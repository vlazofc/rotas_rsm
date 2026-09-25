"""Normalização e validação de CPF/CNPJ compartilhadas entre carriers e access_model.

Fonte única de verdade: antes existiam duas implementações divergentes
(carriers/router.py aceitava CPF ou CNPJ; access_model/router.py exigia
sempre 14 dígitos), o que bloqueava transportadoras pessoa física de serem
vinculadas a uma filial mesmo com cadastro válido.
"""


def normalize_document(document: str | None) -> str:
    return "".join(filter(str.isdigit, document or ""))


def is_valid_document(document: str | None, person_type: str | None = None) -> bool:
    digits = normalize_document(document)
    if person_type == "pessoa_fisica":
        return len(digits) == 11
    if person_type == "pessoa_juridica":
        return len(digits) == 14
    return len(digits) in (11, 14)
