import graphql
from typing import Any
from graphql import GraphQLResolveInfo


def make_executable_schema(schema_definition, resolvers):
    ast = graphql.parse(schema_definition)
    schema = graphql.build_ast_schema(ast)

    for type_name in resolvers:
        field_type = schema.get_type(type_name)

        for field_name in resolvers[type_name]:
            if field_type is graphql.GraphQLScalarType:
                field_type.fields[field_name].resolve = resolvers[type_name][field_name]
                continue

            field = field_type.fields[field_name]
            field.resolve = resolvers[type_name][field_name]

        if not field_type.fields:
            continue

        for remaining in field_type.fields:
            if field_type.fields[remaining].resolve is None:
                field_type.fields[remaining].resolve = default_resolver

    return schema


def default_resolver(source: Any, info: GraphQLResolveInfo, **args: Any) -> Any:
    field_name = info.field_name
    value = (
        source.get(field_name)
        if isinstance(source, dict)
        else getattr(source, field_name, None)
    )
    if callable(value):
        return value(info, **args)
    return value
