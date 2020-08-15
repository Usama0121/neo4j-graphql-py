import unittest

from tests.helpers.cypher_test_helpers import augmented_schema
from graphql import print_schema


class TestAugmentedSchema(unittest.TestCase):

    def test_augmented_schema(self):
        schema = augmented_schema()
        expected_schema = '''directive @cypher(statement: String!) on FIELD_DEFINITION

directive @relation(name: String!, direction: String!) on FIELD_DEFINITION

directive @MutationMeta(relationship: String, from: String, to: String) on FIELD_DEFINITION

type Actor implements Person {
  id: ID!
  name: String
  movies: [Movie]
}

type Book {
  genre: BookGenre
}

enum BookGenre {
  Mystery
  Science
  Math
}

type Genre {
  _id: ID!
  name: String
  movies(first: Int = 3, offset: Int = 0): [Movie]
  highestRatedMovie: Movie
}

type Movie {
  _id: ID
  movieId: ID!
  title: String
  year: Int
  plot: String
  poster: String
  imdbRating: Float
  genres: [Genre]
  similar(first: Int = 3, offset: Int = 0): [Movie]
  mostSimilar: Movie
  degree: Int
  actors(first: Int = 3, offset: Int = 0, name: String): [Actor]
  avgStars: Float
  filmedIn: State
  scaleRating(scale: Int = 3): Float
  scaleRatingFloat(scale: Float = 1.5): Float
  actorMovies: [Movie]
}

type Mutation {
  CreateMovie(movieId: ID, title: String, year: Int, plot: String, poster: String, imdbRating: Float, degree: Int, avgStars: Float, scaleRating: Float, scaleRatingFloat: Float): Movie
  AddMovieGenre(movie_id: ID!, genre_id: ID!): Movie
  AddActorMovie(actorid: ID!, movie_id: ID!): Actor
  AddMovieState(movie_id: ID!, statename: String!): Movie
  CreateGenre(name: String): Genre
  CreateActor(id: ID, name: String): Actor
  CreateState(name: String): State
  CreateBook(genre: BookGenre): Book
  CreateUser(id: ID, name: String): User
}

interface Person {
  id: ID!
  name: String
}

type Query {
  Movie(_id: Int, id: ID, title: String, year: Int, plot: String, poster: String, imdbRating: Float, first: Int, offset: Int): [Movie]
  MoviesByYear(year: Int): [Movie]
  MovieById(movieId: ID!): Movie
  MovieBy_Id(_id: Int!): Movie
  GenresBySubstring(substring: String): [Genre]
  Books: [Book]
}

type State {
  name: String
}

type User implements Person {
  id: ID!
  name: String
}
'''
        self.assertEqual(expected_schema, print_schema(schema))
