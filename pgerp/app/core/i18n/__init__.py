"""PyGo ERP V2.0 — Internationalization (i18n) module.

Provides translation support for ES/EN/PT.
"""
import os
import json
from pathlib import Path

# Supported languages
SUPPORTED_LANGS = ["es", "en", "pt"]
DEFAULT_LANG = "es"

# Translation dictionaries
TRANSLATIONS = {
    "es": {
        "app_name": "PyGo ERP",
        "dashboard": "Tablero",
        "inventory": "Inventario",
        "sales": "Ventas",
        "purchases": "Compras",
        "accounting": "Contabilidad",
        "crm": "CRM",
        "projects": "Proyectos",
        "reports": "Reportes",
        "login": "Iniciar Sesión",
        "logout": "Cerrar Sesión",
        "email": "Correo electrónico",
        "password": "Contraseña",
        "submit": "Enviar",
        "cancel": "Cancelar",
        "create": "Crear",
        "update": "Actualizar",
        "delete": "Eliminar",
        "edit": "Editar",
        "save": "Guardar",
        "search": "Buscar",
        "filter": "Filtrar",
        "export": "Exportar",
        "import": "Importar",
        "actions": "Acciones",
        "name": "Nombre",
        "description": "Descripción",
        "status": "Estado",
        "date": "Fecha",
        "total": "Total",
        "quantity": "Cantidad",
        "price": "Precio",
        "client": "Cliente",
        "product": "Producto",
        "order": "Orden",
        "invoice": "Factura",
        "lead": "Prospecto",
        "opportunity": "Oportunidad",
        "task": "Tarea",
        "project": "Proyecto",
        "time": "Tiempo",
        "settings": "Configuración",
        "profile": "Perfil",
        "users": "Usuarios",
        "companies": "Compañías",
        "active": "Activo",
        "inactive": "Inactivo",
        "pending": "Pendiente",
        "completed": "Completado",
        "cancelled": "Cancelado",
        "draft": "Borrador",
        "confirmed": "Confirmado",
        "delivered": "Entregado",
        "invoiced": "Facturado",
        "paid": "Pagado",
        "unpaid": "No pagado",
        "error_required": "Este campo es requerido",
        "error_invalid_email": "Correo electrónico inválido",
        "error_invalid_password": "Contraseña inválida (mínimo 8 caracteres)",
        "success_created": "Creado exitosamente",
        "success_updated": "Actualizado exitosamente",
        "success_deleted": "Eliminado exitosamente",
        "confirm_delete": "¿Está seguro de eliminar este registro?",
        "no_records": "No hay registros",
        "loading": "Cargando...",
        "language": "Idioma",
    },
    "en": {
        "app_name": "PyGo ERP",
        "dashboard": "Dashboard",
        "inventory": "Inventory",
        "sales": "Sales",
        "purchases": "Purchases",
        "accounting": "Accounting",
        "crm": "CRM",
        "projects": "Projects",
        "reports": "Reports",
        "login": "Log In",
        "logout": "Log Out",
        "email": "Email",
        "password": "Password",
        "submit": "Submit",
        "cancel": "Cancel",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "edit": "Edit",
        "save": "Save",
        "search": "Search",
        "filter": "Filter",
        "export": "Export",
        "import": "Import",
        "actions": "Actions",
        "name": "Name",
        "description": "Description",
        "status": "Status",
        "date": "Date",
        "total": "Total",
        "quantity": "Quantity",
        "price": "Price",
        "client": "Client",
        "product": "Product",
        "order": "Order",
        "invoice": "Invoice",
        "lead": "Lead",
        "opportunity": "Opportunity",
        "task": "Task",
        "project": "Project",
        "time": "Time",
        "settings": "Settings",
        "profile": "Profile",
        "users": "Users",
        "companies": "Companies",
        "active": "Active",
        "inactive": "Inactive",
        "pending": "Pending",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "draft": "Draft",
        "confirmed": "Confirmed",
        "delivered": "Delivered",
        "invoiced": "Invoiced",
        "paid": "Paid",
        "unpaid": "Unpaid",
        "error_required": "This field is required",
        "error_invalid_email": "Invalid email address",
        "error_invalid_password": "Invalid password (minimum 8 characters)",
        "success_created": "Created successfully",
        "success_updated": "Updated successfully",
        "success_deleted": "Deleted successfully",
        "confirm_delete": "Are you sure you want to delete this record?",
        "no_records": "No records found",
        "loading": "Loading...",
        "language": "Language",
    },
    "pt": {
        "app_name": "PyGo ERP",
        "dashboard": "Painel",
        "inventory": "Inventário",
        "sales": "Vendas",
        "purchases": "Compras",
        "accounting": "Contabilidade",
        "crm": "CRM",
        "projects": "Projetos",
        "reports": "Relatórios",
        "login": "Entrar",
        "logout": "Sair",
        "email": "E-mail",
        "password": "Senha",
        "submit": "Enviar",
        "cancel": "Cancelar",
        "create": "Criar",
        "update": "Atualizar",
        "delete": "Excluir",
        "edit": "Editar",
        "save": "Salvar",
        "search": "Pesquisar",
        "filter": "Filtrar",
        "export": "Exportar",
        "import": "Importar",
        "actions": "Ações",
        "name": "Nome",
        "description": "Descrição",
        "status": "Status",
        "date": "Data",
        "total": "Total",
        "quantity": "Quantidade",
        "price": "Preço",
        "client": "Cliente",
        "product": "Produto",
        "order": "Pedido",
        "invoice": "Fatura",
        "lead": "Lead",
        "opportunity": "Oportunidade",
        "task": "Tarefa",
        "project": "Projeto",
        "time": "Tempo",
        "settings": "Configurações",
        "profile": "Perfil",
        "users": "Usuários",
        "companies": "Empresas",
        "active": "Ativo",
        "inactive": "Inativo",
        "pending": "Pendente",
        "completed": "Concluído",
        "cancelled": "Cancelado",
        "draft": "Rascunho",
        "confirmed": "Confirmado",
        "delivered": "Entregue",
        "invoiced": "Faturado",
        "paid": "Pago",
        "unpaid": "Não pago",
        "error_required": "Este campo é obrigatório",
        "error_invalid_email": "E-mail inválido",
        "error_invalid_password": "Senha inválida (mínimo 8 caracteres)",
        "success_created": "Criado com sucesso",
        "success_updated": "Atualizado com sucesso",
        "success_deleted": "Excluído com sucesso",
        "confirm_delete": "Tem certeza de que deseja excluir este registro?",
        "no_records": "Nenhum registro encontrado",
        "loading": "Carregando...",
        "language": "Idioma",
    },
}


def get_lang():
    """Get current language from environment or default."""
    return os.environ.get("PYGO_LANG", DEFAULT_LANG)


def set_lang(lang):
    """Set current language."""
    if lang in SUPPORTED_LANGS:
        os.environ["PYGO_LANG"] = lang
        return True
    return False


def t(key, lang=None):
    """Translate a key."""
    lang = lang or get_lang()
    translations = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    return translations.get(key, key)


def translate(text, source_lang="en", target_lang=None):
    """Simple translation lookup (for static text in templates)."""
    target_lang = target_lang or get_lang()
    if target_lang == source_lang:
        return text
    
    # Look up in reverse mapping
    en_dict = TRANSLATIONS.get(source_lang, {})
    target_dict = TRANSLATIONS.get(target_lang, {})
    
    # Find key for source text
    for key, value in en_dict.items():
        if value.lower() == text.lower():
            return target_dict.get(key, text)
    
    return text


def get_all_translations(lang=None):
    """Get all translations for a language."""
    lang = lang or get_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
