import re
import json
import logging
from typing import Any
from pydash import find, reduce_
from graphql import GraphQLResolveInfo, GraphQLScalarType, parse, build_ast_schema

logger = logging.getLogger('neo4j_graphql_py')


def make_executable_schema(schema_definition, resolvers):
    ast = parse(schema_definition)
    schema = build_ast_schema(ast, assume_valid=True)

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


def is_mutation(resolve_info):
    return resolve_info.operation.operation == 'mutation'


def is_add_relationship_mutation(resolve_info):
    return (is_mutation(resolve_info)
            and
            (resolve_info.field_name.starts('add')
             or resolve_info.field_name.startswith('Add'))
            )


def type_identifiers(return_type):
    type_name = str(inner_type(return_type))
    return {'variable_name': low_first_letter(type_name),
            'type_name': type_name}


def is_graphql_scalar_type(field_type):
    return type(field_type).__name__ == 'GraphQLScalarType' or type(field_type).__name__ == 'GraphQLEnumType'


def is_array_type(field_type):
    return str(field_type).startswith('[')


def low_first_letter(word):
    return word[0].lower() + word[1:]


def inner_type(field_type):
    return inner_type(field_type.of_type) if getattr(field_type, 'of_type', None) else field_type


def directive_with_args(directive_name, *args):
    def fun(schema_type, field_name):
        def field_directive(schema_type, field_name, directive_name):
            return find(schema_type.fields[field_name].ast_node.directives, lambda d: d.name.value == directive_name)

        def directive_argument(directive, name):
            return find(directive.arguments, lambda a: a.name.value == name).value.value

        directive = field_directive(schema_type, field_name, directive_name)
        ret = {}
        if directive:
            ret.update({key: directive_argument(directive, key) for key in args})
        return ret

    return fun


cypher_directive = directive_with_args('cypher', 'statement')
relation_directive = directive_with_args('relation', 'name', 'direction')
mutation_meta_directive = directive_with_args('MutationMeta', 'relationship', 'from', 'to')


def inner_filter_params(selections):
    query_params = {}
    if len(selections.arguments) > 0:
        query_params = {arg.name.value: arg.value.value for arg in selections.arguments if
                        arg.name.value not in ['first', 'offset']}
    # FIXME: support IN for multiple values -> WHERE
    query_params = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(query_params))

    return query_params


def argument_value(selection, name, variable_values):
    arg = find(selection.arguments, lambda argument: argument.name.value == name)
    return (
        None if arg is None
        else variable_values[name] if getattr(arg.value, 'value', None) is None
                                      and name in variable_values and arg.value.kind == 'variable'
        else arg.value.value
    )


def extract_query_result(records, return_type):
    type_ident = type_identifiers(return_type)
    variable_name = type_ident.get('variable_name')
    result = [record.get(variable_name) for record in records.data()]
    return result if is_array_type(return_type) else result[0] if len(result) > 0 else None


def compute_skip_limit(selection, variable_values):
    first = argument_value(selection, "first", variable_values)
    offset = argument_value(selection, "offset", variable_values)
    if first is None and offset is None:
        return ""
    if offset is None:
        return f'[..{first}]'
    if first is None:
        return f'[{offset}..]'
    return f'[{offset}..{int(offset) + int(first)}]'


def extract_selections(selections, fragments):
    # extract any fragment selection sets into a single array of selections
    return reduce_(selections,
                   lambda acc, curr:
                   [*acc, *fragments[curr.name.value].selection_set.selections] if curr.kind == 'fragment_spread'
                   else [*acc, curr],
                   [])
