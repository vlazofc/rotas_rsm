from app.workers.celery_app import celery_app
result = celery_app.AsyncResult("ROUTE_TASK_ID")
print(result.state)
print(result.result if result.ready() else "processing")
