"""Caixa transversal de tarefas, transferências e trilha imutável."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access
from app.db.models import (
    Expense, MaintenanceOrder, PurchaseTicket, RouteOccurrence, User,
    VehicleChangeRequest, WorkflowTask, WorkflowTaskEvent,
)
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log

router = APIRouter(prefix="/workflow", tags=["workflow"])
MANAGERS = {Role.ADMIN_GLOBAL.value, Role.GESTOR_BRASIL.value}
DEPARTMENTS = {"Operação", "Torre de controle", "Frota", "Financeiro", "Compras", "Cadastros", "Diretoria"}


def _event(db: Session, task: WorkflowTask, actor_id: int | None, action: str, note: str | None = None,
           old_department: str | None = None, old_status: str | None = None):
    db.add(WorkflowTaskEvent(task_id=task.id, actor_id=actor_id, action=action,
        from_department=old_department, to_department=task.current_department,
        from_status=old_status, to_status=task.status, note=note))


def _ensure(db: Session, tenant_id: int | None, branch_id: int, source_type: str, source_id: int,
            title: str, description: str | None, requester_id: int | None, department: str, source_status: str):
    if requester_id is None: return
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.tenant_id == tenant_id,
        WorkflowTask.source_type == source_type, WorkflowTask.source_id == source_id))
    if task is None:
        task = WorkflowTask(tenant_id=tenant_id, branch_id=branch_id, source_type=source_type,
            source_id=source_id, title=title, description=description, requester_id=requester_id,
            current_department=department, status="open", source_status=source_status)
        db.add(task); db.flush(); _event(db, task, requester_id, "created", "Ticket criado a partir do fluxo de origem.")
    elif task.source_status != source_status:
        previous = task.source_status; task.source_status = source_status
        _event(db, task, None, "source_status_changed", f"Origem: {previous or '—'} → {source_status}")


def _sync(db: Session, user: User):
    branch = user.branch_id
    if branch is None: return
    for row in db.scalars(select(RouteOccurrence).where(RouteOccurrence.branch_id == branch)).all():
        _ensure(db,row.tenant_id,row.branch_id,"occurrence",row.id,f"Ocorrência de rota #{row.id}",row.description,row.reported_by,"Operação",row.status)
    for row in db.scalars(select(Expense).where(Expense.branch_id == branch)).all():
        department = "Financeiro" if row.approval_status in {"pending", "in_review"} else ((db.get(User,row.user_id).department or "Solicitante") if row.user_id else "Solicitante")
        _ensure(db,row.tenant_id,row.branch_id,"expense",row.id,f"Análise de despesa #{row.id}",row.notes,row.user_id,department,row.approval_status)
        task=db.scalar(select(WorkflowTask).where(WorkflowTask.tenant_id==row.tenant_id,WorkflowTask.source_type=="expense",WorkflowTask.source_id==row.id))
        if task and task.current_department!=department:
            previous=task.current_department;task.current_department=department;task.current_assignee_id=None
            _event(db,task,None,"routed_by_source",f"Fluxo da despesa: {previous} → {department}")
        target = "returned" if row.approval_status=="adjustment_requested" else ("closed" if row.approval_status in {"approved","rejected"} else None)
        if task and target and task.status!=target:
            old=task.status;task.status=target;task.current_assignee_id=task.requester_id if target=="returned" else None
            if target=="closed":task.closed_at=datetime.now(timezone.utc)
            _event(db,task,None,"returned_by_source" if target=="returned" else "closed_by_source",f"Situação financeira: {row.approval_status}",task.current_department,old)
    for row in db.scalars(select(PurchaseTicket).where(PurchaseTicket.branch_id == branch)).all():
        if row.status=="aguardando_aprovacao": department="Financeiro"
        elif row.status in {"ajuste_solicitado","rejeitada","recebida"}: department=row.department or "Operação"
        else: department="Compras"
        _ensure(db,row.tenant_id,row.branch_id,"purchase",row.id,f"Compra {row.ticket}",row.description,row.requester_id,department,row.status)
        task=db.scalar(select(WorkflowTask).where(WorkflowTask.tenant_id==row.tenant_id,WorkflowTask.source_type=="purchase",WorkflowTask.source_id==row.id))
        if task and task.source_status==row.status and task.current_department!=department:
            previous=task.current_department;task.current_department=department;task.current_assignee_id=None
            _event(db,task,None,"routed_by_source",f"Fluxo de Compras: {previous} → {department}")
        if task and row.status in {"ajuste_solicitado","rejeitada","recebida"} and task.status not in {"returned","closed"}:
            previous_status=task.status;task.status="returned";task.current_assignee_id=None
            _event(db,task,None,"returned_by_source",f"Resultado devolvido ao solicitante: {row.status}",previous_status,"returned")
    for row in db.scalars(select(MaintenanceOrder).where(MaintenanceOrder.branch_id == branch)).all():
        _ensure(db,row.tenant_id,row.branch_id,"maintenance_order",row.id,f"Ordem de serviço #{row.id}",row.description,row.created_by,"Frota",row.status)
    for row in db.scalars(select(VehicleChangeRequest).where(VehicleChangeRequest.branch_id == branch)).all():
        _ensure(db,row.tenant_id,row.branch_id,"vehicle_change",row.id,f"Alteração de veículo #{row.vehicle_id}",row.reason,row.requested_by_id,"Cadastros",row.status)
    db.commit()


def _access(db: Session, user: User, task_id: int) -> WorkflowTask:
    task=db.get(WorkflowTask,task_id)
    if task is None: raise HTTPException(404,"Tarefa não encontrada.")
    require_branch_access(db,user,task.branch_id)
    department=(user.department or "").casefold()
    if user.role not in MANAGERS and task.requester_id!=user.id and task.current_assignee_id!=user.id and task.current_department.casefold()!=department:
        raise HTTPException(403,"Tarefa restrita ao solicitante, responsável ou setor atual.")
    return task


def _out(db: Session, task: WorkflowTask):
    requester=db.get(User,task.requester_id); assignee=db.get(User,task.current_assignee_id) if task.current_assignee_id else None
    return {**task.__dict__,"requester_name":requester.name if requester else None,"assignee_name":assignee.name if assignee else None}


@router.get("/tasks")
def tasks(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _sync(db,user)
    stmt=select(WorkflowTask).where(WorkflowTask.branch_id==user.branch_id)
    if user.role not in MANAGERS:
        stmt=stmt.where(or_(WorkflowTask.requester_id==user.id,WorkflowTask.current_assignee_id==user.id,
            WorkflowTask.current_department.ilike(user.department or "__none__")))
    if status: stmt=stmt.where(WorkflowTask.status==status)
    return [_out(db,row) for row in db.scalars(stmt.order_by(WorkflowTask.updated_at.desc())).all()]


@router.get("/tasks/{task_id}/history")
def history(task_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=_access(db,user,task_id)
    rows=db.execute(select(WorkflowTaskEvent,User.name).outerjoin(User,User.id==WorkflowTaskEvent.actor_id)
        .where(WorkflowTaskEvent.task_id==task.id).order_by(WorkflowTaskEvent.created_at)).all()
    return [{**event.__dict__,"actor_name":actor} for event,actor in rows]


class StartIn(BaseModel):
    note:str|None=Field(default=None,max_length=2000)

@router.post("/tasks/{task_id}/start")
def start(task_id:int,data:StartIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=_access(db,user,task_id)
    if task.status not in {"open","in_progress"}:raise HTTPException(409,"Tarefa não está disponível para início.")
    old=task.status;task.status="in_progress";task.current_assignee_id=user.id
    _event(db,task,user.id,"started",data.note,task.current_department,old);db.commit();return _out(db,task)


class TransferIn(BaseModel):
    department:str=Field(min_length=2,max_length=80);assignee_id:int|None=None;note:str=Field(min_length=5,max_length=2000)

@router.post("/tasks/{task_id}/transfer")
def transfer(task_id:int,data:TransferIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=_access(db,user,task_id)
    if task.status in {"returned","closed","cancelled"}:raise HTTPException(409,"Tarefa não pode mais ser transferida.")
    if data.department not in DEPARTMENTS:raise HTTPException(422,"Setor de destino inválido.")
    assignee=db.get(User,data.assignee_id) if data.assignee_id else None
    if assignee and (assignee.tenant_id!=task.tenant_id or assignee.branch_id!=task.branch_id):raise HTTPException(422,"Responsável fora da empresa/filial.")
    old_department,old_status=task.current_department,task.status
    task.current_department,task.current_assignee_id,task.status=data.department,data.assignee_id,"open"
    _event(db,task,user.id,"transferred",data.note,old_department,old_status)
    log(db,user_id=user.id,action="transfer",entity="workflow_task",entity_id=task.id,detail=f"{old_department} -> {data.department}; {data.note}")
    db.commit();return _out(db,task)


class ReturnIn(BaseModel):
    resolution:str=Field(min_length=5,max_length=4000)

@router.post("/tasks/{task_id}/return")
def return_to_requester(task_id:int,data:ReturnIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=_access(db,user,task_id)
    if task.status not in {"open","in_progress"}:raise HTTPException(409,"Tarefa não está em tratamento.")
    if task.source_type=="expense":
        expense=db.get(Expense,task.source_id)
        if expense is None:raise HTTPException(404,"Despesa vinculada não encontrada.")
        if expense.approval_status not in {"pending","in_review"}:raise HTTPException(409,"A despesa já foi finalizada e não pode ser devolvida para ajuste.")
        expense.approval_status="adjustment_requested";expense.decision_note=data.resolution
        expense.reviewed_by_id=user.id;expense.reviewed_at=datetime.now(timezone.utc)
    old_department,old_status=task.current_department,task.status
    requester=db.get(User,task.requester_id);task.current_department=requester.department or "Solicitante"
    task.current_assignee_id=task.requester_id;task.status="returned";task.resolution=data.resolution
    task.returned_at=datetime.now(timezone.utc);_event(db,task,user.id,"returned",data.resolution,old_department,old_status)
    db.commit();return _out(db,task)


class CloseIn(BaseModel):
    note:str|None=Field(default=None,max_length=2000)

@router.post("/tasks/{task_id}/close")
def close(task_id:int,data:CloseIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=_access(db,user,task_id)
    if task.requester_id!=user.id and user.role not in MANAGERS:raise HTTPException(403,"Somente o solicitante pode finalizar o ticket.")
    if task.status!="returned":raise HTTPException(409,"O setor responsável ainda não devolveu a tratativa.")
    old=task.status;task.status="closed";task.closed_at=datetime.now(timezone.utc);task.closed_by_id=user.id
    _event(db,task,user.id,"closed",data.note or "Tratativa aceita pelo solicitante.",task.current_department,old)
    log(db,user_id=user.id,action="close",entity="workflow_task",entity_id=task.id,detail=data.note);db.commit();return _out(db,task)
