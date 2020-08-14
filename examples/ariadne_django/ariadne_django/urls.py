"""ariadne_django URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from .schema import schema
from django.urls import path
from neo4j import GraphDatabase
from django.contrib import admin
from ariadne.contrib.django.views import GraphQLView

driver = None


def context(request):
    global driver
    if driver is None:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j123"))

    return {'driver': driver, 'request': request}


urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', GraphQLView.as_view(schema=schema, context_value=context), name='graphql'),
]
