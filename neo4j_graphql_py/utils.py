import re
import json
import logging
from typing import Any
from graphql import GraphQLResolveInfo, GraphQLScalarType, parse, build_ast_schema

logger = logging.getLogger('neo4j_graphql_py')


def make_executable_schema(schema_definition, resolvers):
    ast = parse(schema_definition)
    schema = build_ast_schema(ast)

    for type_name in resolvers:
        field_type = schema.get_type(type_name)

        for field_name in resolvers[type_name]:
            if field_type is GraphQLScalarType:
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


def parse_args(args, variable_values):
    if args is None or len(args) == 0:
        return {}

    return {arg.name.value: (
        int(arg.value.value) if arg.value.kind == 'int_value'
        else float(arg.value.value) if arg.value.kind == 'float_value'
        else variable_values[arg.name.value] if arg.value.kind == 'variable'
        else arg.value.value)
        for arg in args}


def get_default_arguments(field_name, schema_type):
    # get default arguments for this field from schema
    args = schema_type.fields[field_name].args
    return {arg_name: arg.default_value for arg_name, arg in args.items()}


def cypher_directive_args(variable, head_selection, schema_type, resolve_info):
    default_args = get_default_arguments(head_selection.name.value, schema_type)
    schema_args = {}
    query_args = parse_args(head_selection.arguments, resolve_info.variable_values)
    default_args.update(query_args)
    args = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(default_args))
    return f'{{this: {variable}{args[1:]}' if args == "{}" else f'{{this: {variable}, {args[1:]}'
