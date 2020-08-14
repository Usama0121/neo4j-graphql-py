import unittest
from graphql import graphql_sync
from neo4j_graphql_py import cypher_query, make_executable_schema


class Test(unittest.TestCase):

    def _test_runner(self, graphql_query, expected_cypher_query):
        test_movie_schema = '''
        directive @cypher(statement: String!) on FIELD_DEFINITION
        directive @relation(name:String!, direction:String!) on FIELD_DEFINITION
        type Movie {
            movieId: ID!
            title: String
            year: Int
            plot: String
            poster: String
            imdbRating: Float
            genres: [Genre] @relation(name: "IN_GENRE", direction: "OUT")
            similar(first: Int = 3, offset: Int = 0): [Movie] @cypher(statement: "WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie) RETURN o")
            mostSimilar: Movie @cypher(statement: "WITH {this} AS this RETURN this")
            degree: Int @cypher(statement: "WITH {this} AS this RETURN SIZE((this)--())")
            actors(first: Int = 3, offset: Int = 0, name: String): [Actor] @relation(name: "ACTED_IN", direction:"IN")
            avgStars: Float
            filmedIn: State @relation(name: "FILMED_IN", direction:"OUT")
            scaleRating(scale: Int = 3): Float @cypher(statement: "WITH $this AS this RETURN $scale * this.imdbRating")
            scaleRatingFloat(scale: Float = 1.5): Float @cypher(statement: "WITH $this AS this RETURN $scale * this.imdbRating")
            actorMovies: [Movie] @cypher(statement: "MATCH (this)-[:ACTED_IN*2]-(other:Movie) RETURN other")
        }
        type Genre {
            name: String
            movies(first: Int = 3, offset: Int = 0): [Movie] @relation(name: "IN_GENRE", direction: "IN")
            highestRatedMovie: Movie @cypher(statement: "MATCH (m:Movie)-[:IN_GENRE]->(this) RETURN m ORDER BY m.imdbRating DESC LIMIT 1")
        }
        type State {
            name: String
        }
        interface Person {
            id: ID!
            name: String
        }
        type Actor implements Person {
            id: ID!
            name: String
            movies: [Movie] @relation(name: "ACTED_IN", direction:"OUT")
        }
        type User implements Person {
            id: ID!
            name: String
        }
        type Query {
            Movie(_id: Int, id: ID, title: String, year: Int, plot: String, poster: String, imdbRating: Float, first: Int, offset: Int): [Movie]
            MoviesByYear(year: Int): [Movie]
            MovieById(movieId: ID!): Movie
            MovieBy_Id(_id: Int): Movie
            GenresBySubstring(substring: String): [Genre] @cypher(statement: "MATCH (g:Genre) WHERE toLower(g.name) CONTAINS toLower($substring) RETURN g")
        }
        '''

        def resolve_any(_, info, **kwargs):
            query = cypher_query(info.context, info, **kwargs)
            self.assertEqual(first=query, second=expected_cypher_query)

        resolvers = {
            'Query': {
                'Movie': resolve_any,
                'MoviesByYear': resolve_any,
                'MovieById': resolve_any,
                'MovieBy_Id': resolve_any,
                'GenresBySubstring': resolve_any,
            }
        }

        schema = make_executable_schema(test_movie_schema, resolvers)

        # query the test schema with the test query, assertion is in the resolver
        return graphql_sync(schema, graphql_query)

    def base_test(self, graphql_query, expected_cypher_query):
        results = self._test_runner(graphql_query, expected_cypher_query)
        if results.errors is not None:
            raise results.errors[0].original_error.original_error
        # self.assertIsNone(results.errors)

    def test_simple_cypher_query(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                title
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie { .title } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_simple_skip_limit(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A", first: 1, offset: 0) {
                title
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie { .title , .year } AS movie SKIP 0 LIMIT 1')
        self.base_test(graphql_query, expected_cypher_query)

    def test_cypher_projection_skip_limit(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                title
                actors {
                    name
                }
                similar(first: 3) {
                    title
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie { .title ,'
                                 'actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {}) | movie_actors { .name }] ,'
                                 'similar: [ movie_similar IN apoc.cypher.runFirstColumn("WITH {this} AS this '
                                 'MATCH (this)--(:Genre)--(o:Movie) RETURN o", {this: movie, first: 3, offset: 0}, '
                                 'true) | movie_similar { .title }][..3] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_query_with_name_not_aligning_to_type(self):
        graphql_query = '''
        {
            MoviesByYear(year: 2010) {
                title
            }
        }
        '''
        expected_cypher_query = 'MATCH (movie:Movie {year: 2010}) RETURN movie { .title } AS movie SKIP 0'
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_without_arguments_non_null_type(self):
        graphql_query = '''
        query {
            Movie {
                movieId
            }
        }
        '''
        expected_cypher_query = 'MATCH (movie:Movie {}) RETURN movie { .movieId } AS movie SKIP 0'
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_single_object(self):
        graphql_query = '''
        {
            MovieById(movieId: "18") {
                title
            }
        }
        '''
        expected_cypher_query = 'MATCH (movie:Movie {movieId: "18"}) RETURN movie { .title } AS movie SKIP 0'
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_single_object_relation(self):
        graphql_query = '''
        {
            MovieById(movieId: "3100") {
                title
                filmedIn {
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {movieId: "3100"}) '
                                 'RETURN movie { .title ,'
                                 'filmedIn: head([(movie)-[:FILMED_IN]->(movie_filmedIn:State {}) | '
                                 'movie_filmedIn { .name }]) } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_single_object_array_of_objects_relations(self):
        graphql_query = '''
        {
            MovieById(movieId: "3100") {
                title
                actors {
                    name
                }
                filmedIn {
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {movieId: "3100"}) RETURN movie { .title ,'
                                 'actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {}) | movie_actors { .name }] ,'
                                 'filmedIn: head([(movie)-[:FILMED_IN]->(movie_filmedIn:State {}) | '
                                 'movie_filmedIn { .name }]) } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_deeply_nested_object_query(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                title
                actors {
                    name
                    movies {
                        title
                        actors {
                            name
                            movies {
                                title
                                year
                                similar(first: 3) {
                                    title
                                    year
                                }
                            }
                        }
                    }
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie { .title ,actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {}) | '
                                 'movie_actors { .name ,movies: [(movie_actors)-[:ACTED_IN]'
                                 '->(movie_actors_movies:Movie {}) | movie_actors_movies { .title ,'
                                 'actors: [(movie_actors_movies)<-[:ACTED_IN]-(movie_actors_movies_actors:Actor {}) | '
                                 'movie_actors_movies_actors { .name ,movies: [(movie_actors_movies_actors)-[:ACTED_IN]'
                                 '->(movie_actors_movies_actors_movies:Movie {}) | '
                                 'movie_actors_movies_actors_movies { .title , .year ,'
                                 'similar: [ movie_actors_movies_actors_movies_similar IN apoc.cypher.runFirstColumn("'
                                 'WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie) '
                                 'RETURN o", {this: movie_actors_movies_actors_movies, first: 3, offset: 0}, true) | '
                                 'movie_actors_movies_actors_movies_similar { .title , .year }][..3] }] }] }] }] } '
                                 'AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_meta_field_at_beginning_of_selection_set(self):
        graphql_query = '''
        {
            Movie(title:"River Runs Through It, A") {
                __typename
                title
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie { .title } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_meta_field_at_end_of_selection_set(self):
        graphql_query = '''
        {
            Movie(title:"River Runs Through It, A") {
                title
                __typename
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie {.title } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_meta_field_at_middle_of_selection_set(self):
        graphql_query = '''
        {
            Movie(title:"River Runs Through It, A") {
                title
                __typename
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie { .title , .year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_pass_cypher_directive_default_params_to_sub_query(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                scaleRating
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie {scaleRating: apoc.cypher.runFirstColumn("WITH $this AS this '
                                 'RETURN $scale * this.imdbRating", {this: movie, scale: 3}, false)} AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_pass_cypher_directive_params_to_sub_query(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                scaleRating(scale: 10)
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) '
                                 'RETURN movie {scaleRating: apoc.cypher.runFirstColumn("WITH $this AS this '
                                 'RETURN $scale * this.imdbRating", {this: movie, scale: 10}, false)} AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_cypher_directive_without_any_params(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                mostSimilar {
                    title
                    year
                }
            }
        }
        '''
        expected_cypher_query = (
            'MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie {mostSimilar: '
            'head([ movie_mostSimilar IN apoc.cypher.runFirstColumn("WITH {this} AS this RETURN this", '
            '{this: movie}, true) | movie_mostSimilar { .title , .year }]) } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_by_internal_neo4j_id(self):
        graphql_query = '''
        {
            Movie(_id: 0) {
                title
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {}) WHERE ID(movie)=0 '
                                 'RETURN movie { .title , .year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    # test('Query for Neo4js internal _id', t=> {
    #   const graphQLQuery = ``,
    #     expectedCypherQuery = ``;
    #   cypherTestRunner(t, graphQLQuery, {}, expectedCypherQuery);
    # });
    def test_query_by_internal_neo4j_id_and_other_params_before_id(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A", _id: 0) {
                title
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) WHERE ID(movie)=0 '
                                 'RETURN movie { .title , .year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_by_internal_neo4j_id_and_other_params_after_id(self):
        graphql_query = '''
        {
            Movie(_id: 0, year: 2010) {
                title
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {year: 2010}) WHERE ID(movie)=0 '
                                 'RETURN movie { .title , .year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_by_internal_neo4j_id_by_dedicated_query_MovieBy_Id(self):
        graphql_query = '''
        {
            MovieBy_Id(_id: 0) {
                title
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {}) WHERE ID(movie)=0 '
                                 'RETURN movie { .title , .year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_query_with_indirect_relation(self):
        graphql_query = '''
        {
            Movie(title: "Top Gun") {
                actorMovies {
                    title
                    actors { 
                        name 
                    }
                }
            }
        }
        '''

        expected_cypher_query = (
            'MATCH (movie:Movie {title: "Top Gun"}) RETURN movie {actorMovies: [ movie_actorMovies '
            'IN apoc.cypher.runFirstColumn("MATCH (this)-[:ACTED_IN*2]-(other:Movie) RETURN other", '
            '{this: movie}, true) | movie_actorMovies { .title ,actors: [(movie_actorMovies)<-[:ACTED_IN]-'
            '(movie_actorMovies_actors:Actor {}) | movie_actorMovies_actors { .name }] }] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_cypher_subquery_filters(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                title
                actors(name: "Tom Hanks") {
                    name
                }
                similar(first: 3) {
                    title
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie '
                                 '{ .title ,actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {name: "Tom Hanks"}) | '
                                 'movie_actors { .name }] ,similar: [ movie_similar IN apoc.cypher.runFirstColumn('
                                 '"WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie) RETURN o", {this: movie, '
                                 'first: 3, offset: 0}, true) | movie_similar { .title }][..3] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_cypher_subquery_filters_with_paging(self):
        graphql_query = '''
        {
            Movie(title: "River Runs Through It, A") {
                title
                actors(name: "Tom Hanks", first: 3) {
                    name
                }
                similar(first: 3) {
                    title
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie '
                                 '{ .title ,actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {name: "Tom Hanks"}) | '
                                 'movie_actors { .name }][..3] ,similar: [ movie_similar IN apoc.cypher.'
                                 'runFirstColumn("WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie) RETURN o", '
                                 '{this: movie, first: 3, offset: 0}, true) | movie_similar { .title }][..3] } '
                                 'AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_cypher_directive_on_query_type(self):
        graphql_query = '''
        {
            GenresBySubstring(substring:"Action") {
                name
                movies(first: 3) {
                    title
                }
            }
        }
        '''
        expected_cypher_query = ('WITH apoc.cypher.runFirstColumn("MATCH (g:Genre) WHERE toLower(g.name) '
                                 'CONTAINS toLower($substring) RETURN g", {substring: "Action"}, true) AS x '
                                 'UNWIND x AS genre RETURN genre { .name ,movies: [(genre)<-[:IN_GENRE]-'
                                 '(genre_movies:Movie {}) | genre_movies { .title }][..3] } AS genre SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)


if __name__ == '__main__':
    unittest.main()
