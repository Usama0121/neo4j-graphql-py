import os
from api.queries import query
from django.conf import settings
from ariadne import make_executable_schema, load_schema_from_path

type_defs = load_schema_from_path(os.path.join(settings.BASE_DIR, 'api', 'schema.graphql'))

schema = make_executable_schema(type_defs, query)
