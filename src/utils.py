import contextvars

request_id_var = contextvars.ContextVar('request_id')

def set_request_id(request_id):
    request_id_var.set(request_id)

def get_request_id():
    try:
        return request_id_var.get()
    except LookupError:
        return None
