import unittest
from tests.helpers.cypher_test_helpers import test_runner, augmented_schema_cypher_test_runner


class TestSchema(unittest.TestCase):

    def base_test(self, graphql_query, expected_cypher_query, params=None):
        results = test_runner(self, graphql_query, expected_cypher_query, params)
        if results.errors is not None:
            raise results.errors[0]
        results = augmented_schema_cypher_test_runner(self, graphql_query, expected_cypher_query, params)
        if results.errors is not None:
            raise results.errors[0]
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

    def test_handle_cypher_directive_on_mutation_type(self):
        graphql_query = '''
        mutation someMutation {
            CreateGenre(name: "Wildlife Documentary") {
                name
            }
        }
        '''
        expected_cypher_query = ('CALL apoc.cypher.doIt("CREATE (g:Genre) SET g.name = $name RETURN g", '
                                 '{name: "Wildlife Documentary"}) YIELD value WITH apoc.map.values(value, '
                                 '[keys(value)[0]])[0] AS genre RETURN genre { .name } AS genre SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_create_node_mutation_type(self):
        graphql_query = '''
        mutation someMutation {
            CreateMovie(movieId: "12dd334d5", title:"My Super Awesome Movie", year:2018, plot:"An unending saga", poster:"www.movieposter.com/img.png", imdbRating: 1.0) {
                _id
                title
                genres {
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('CREATE (movie:Movie) SET movie = $params RETURN movie {_id: ID(movie), .title ,'
                                 'genres: [(movie)-[:IN_GENRE]->(movie_genres:Genre {}) | movie_genres { .name }] } '
                                 'AS movie')
        self.base_test(graphql_query, expected_cypher_query)

    def test_add_relation_mutation(self):
        graphql_query = '''
        mutation someMutation {
            AddMovieGenre(moviemovieId:"123", genrename: "Action") {
                _id
                title
                genres {
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {movieId: $movieId}) '
                                 'MATCH (genre:Genre {name: $name}) '
                                 'CREATE (movie)-[:IN_GENRE]->(genre) '
                                 'RETURN movie {_id: ID(movie), .title ,genres: '
                                 '[(movie)-[:IN_GENRE]->(movie_genres:Genre {}) | movie_genres { .name }] } AS movie')
        self.base_test(graphql_query, expected_cypher_query)

    def test_add_relation_mutation_with_graphql_variables(self):
        graphql_query = '''
        mutation someMutation($movieParam:ID!) {
            AddMovieGenre(moviemovieId:$movieParam, genrename: "Action") {
                _id
                title
                genres {
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {movieId: $movieId}) '
                                 'MATCH (genre:Genre {name: $name}) '
                                 'CREATE (movie)-[:IN_GENRE]->(genre) '
                                 'RETURN movie {_id: ID(movie), .title ,genres: '
                                 '[(movie)-[:IN_GENRE]->(movie_genres:Genre {}) | movie_genres { .name }] } AS movie')
        self.base_test(graphql_query, expected_cypher_query, params={'movieParam': '123'})

    def test_handle_graphql_variables_in_nested_selection_first(self):
        graphql_query = '''
        query ($first: Int!,$year: Int!) {
            Movie(year: $year) {
                title
                year
                similar(first: $first) {
                    title
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {year: 2016}) RETURN movie { .title , .year ,'
                                 'similar: [ movie_similar IN apoc.cypher.runFirstColumn("WITH {this} AS this '
                                 'MATCH (this)--(:Genre)--(o:Movie) RETURN o", {this: movie, first: 3, offset: 0}, '
                                 'true) | movie_similar { .title }][..3] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query, params={'year': 2016, 'first': 3})

    def test_handle_graphql_variables_in_nested_selection_cypher(self):
        graphql_query = '''
        query ($year: Int = 2016, $first: Int = 2, $scale:Int) {
            Movie(year: $year) {
                title
                year
                similar(first: $first) {
                    title
                    scaleRating(scale:$scale) 
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {year: 2016}) RETURN movie { .title , .year ,'
                                 'similar: [ movie_similar IN apoc.cypher.runFirstColumn("WITH {this} AS this '
                                 'MATCH (this)--(:Genre)--(o:Movie) RETURN o", {this: movie, first: 3, offset: 0}, '
                                 'true) | movie_similar { .title ,scaleRating: apoc.cypher.runFirstColumn("'
                                 'WITH $this AS this RETURN $scale * this.imdbRating", {this: movie_similar, scale: 5},'
                                 ' false)}][..3] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query, params={'year': 2016, 'first': 3, 'scale': 5})

    def test_return_internal_node_id(self):
        graphql_query = '''
        {
            Movie(year: 2016) {
                _id
                title
                year
                genres {
                    _id
                    name
                }
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {year: 2016}) RETURN movie {_id: ID(movie), .title , .year ,'
                                 'genres: [(movie)-[:IN_GENRE]->(movie_genres:Genre {}) | '
                                 'movie_genres {_id: ID(movie_genres), .name }] } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query, params={'year': 2016, 'first': 3, 'scale': 5})

    def test_enum_as_scalar(self):
        graphql_query = '''
        {
            Books {
                genre
            }
        }
        '''
        expected_cypher_query = 'MATCH (book:Book {}) RETURN book { .genre } AS book SKIP 0'
        self.base_test(graphql_query, expected_cypher_query, params={'year': 2016, 'first': 3, 'scale': 5})

    def test_handle_query_fragment(self):
        graphql_query = '''
        fragment myTitle on Movie {
            title
            actors {
                name
            }
        }
        query getMovie {
            Movie(title: "River Runs Through It, A") {
                ...myTitle
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie { .title ,'
                                 'actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {}) | movie_actors { .name }] , .year '
                                 '} AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)

    def test_handle_multiple_query_fragment(self):
        graphql_query = '''
        fragment myTitle on Movie {
            title
        }
        fragment myActors on Movie {
            actors {
                name
            }
        }
        query getMovie {
            Movie(title: "River Runs Through It, A") {
                ...myTitle
                ...myActors
                year
            }
        }
        '''
        expected_cypher_query = ('MATCH (movie:Movie {title: "River Runs Through It, A"}) RETURN movie { .title ,'
                                 'actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor {}) | movie_actors { .name }] , '
                                 '.year } AS movie SKIP 0')
        self.base_test(graphql_query, expected_cypher_query)


if __name__ == '__main__':
    unittest.main()
