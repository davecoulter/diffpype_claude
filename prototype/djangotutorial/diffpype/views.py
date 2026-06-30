from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, Http404, JsonResponse, HttpResponseNotFound
from django.urls import reverse_lazy
from .models import *


def index(request):
    # if request.user.is_authenticated:
    #     return HttpResponseRedirect(reverse_lazy('dashboard'))

    diffpype_projects = Project.objects.order_by('name')
    context = {
        "project_list": diffpype_projects,
        "tile":null

    }


    return render(request, 'index.html', context)


def create_project(request):

    proj_name = request.POST["proj_name"]
    p = Project(name=proj_name)
    p.save()

    return HttpResponseRedirect(reverse_lazy("index"))

