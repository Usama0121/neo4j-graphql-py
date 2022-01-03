from unittest import mock

from graphql import graphql_sync, print_schema

from .schema import test_schema
from neo4j_graphql_py import make_executable_schema, augment_schema, cypher_query, cypher_mutation


def run_test(self, graphql_query, expected_cypher_query, params=None):
    test_movie_schema = test_schema + '''
    type Mutation {
        CreateGenre(name: String): Genre @cypher(statement: "CREATE (g:Genre) SET g.name = $name RETURN g")
        CreateMovie(movieId: ID!, title: String, year: Int, plot: String, poster: String, imdbRating: Float): Movie
        AddMovieGenre(moviemovieId: ID!, genrename: String): Movie @MutationMeta(relationship: "IN_GENRE", from:"Movie", to:"Genre")
    }
    '''

    def resolve_query(_, info, **kwargs):
        query = cypher_query(info.context, info, **kwargs)
        self.assertEqual(first=expected_cypher_query, second=query)

    def resolve_mutation(_, info, **kwargs):
        query = cypher_mutation(info.context, info, **kwargs)
        self.assertEqual(first=expected_cypher_query, second=query)

    resolvers = {
        'Query': {
            'Movie': resolve_query,
            'MoviesByYear': resolve_query,
            'MovieById': resolve_query,
            'MovieBy_Id': resolve_query,
            'GenresBySubstring': resolve_query,
            'Books': resolve_query,
        },
        'Mutation': {
            'CreateGenre': resolve_mutation,
            'CreateMovie': resolve_mutation,
            'AddMovieGenre': resolve_mutation,
        }
    }

    schema = make_executable_schema(test_movie_schema, resolvers)

    # query the test schema with the test query, assertion is in the resolver
    return graphql_sync(schema, graphql_query, variable_values=params)


def augmented_schema_cypher_test_runner(self, graphql_query, expected_cypher_query, params=None):
    def resolve_query(_, info, **kwargs):
        query = cypher_query(info.context, info, **kwargs)
        self.assertEqual(first=expected_cypher_query, second=query)

    resolvers = {
        'Query': {
            'Movie': resolve_query,
            'MoviesByYear': resolve_query,
            'MovieById': resolve_query,
            'MovieBy_Id': resolve_query,
            'GenresBySubstring': resolve_query,
            'Books': resolve_query,
        }
    }

    schema = make_executable_schema(test_schema, resolvers)
    aug_schema = augment_schema(schema)

    # query the test schema with the test query, assertion is in the resolver
    return graphql_sync(aug_schema, graphql_query, variable_values=params, context_value=mock.MagicMock())


def augmented_schema():
    schema = make_executable_schema(test_schema, resolvers=[])
    aug_schema = augment_schema(schema)
    return aug_schema
