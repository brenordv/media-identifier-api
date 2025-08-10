import contextvars
from datetime import datetime

request_id_var = contextvars.ContextVar('request_id')

def set_request_id(request_id):
    request_id_var.set(request_id)

def get_request_id():
    try:
        return request_id_var.get()
    except LookupError:
        return None

def is_valid_year(year):
    if year is None:
        return False

    first_movie_ever_release = 195
    current_year = datetime.now().year
    return first_movie_ever_release <= year <= current_year
