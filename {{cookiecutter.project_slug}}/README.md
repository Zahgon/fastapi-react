# {{cookiecutter.project_name}}

## Features

- **Django** + **Django REST Framework** with Python 3.14
- **React 16** with Typescript, Redux, and react-router
- Postgres
- Django ORM with Django migrations
- Pytest for backend tests
- Jest for frontend tests
- Perttier/Eslint (with Airbnb style guide)
- Docker compose for easier development
- Nginx as a reverse proxy to allow backend and frontend on the same port

## Development

The only dependencies for this project should be docker and docker-compose.

### Quick Start

Starting the project with hot-reloading enabled
(the first time it will take a while):

```bash
docker-compose up -d
```

To run the database migrations (for the users table):

```bash
docker-compose run --rm backend python manage.py migrate
```

And navigate to http://localhost:{{cookiecutter.port}}

_Note: If you see an Nginx error at first with a `502: Bad Gateway` page, you may have to wait for webpack to build the development server (the nginx container builds much more quickly)._

### Rebuilding containers:

```
docker-compose build
```

### Restarting containers:

```
docker-compose restart
```

### Bringing containers down:

```
docker-compose down
```

### Frontend Development

Alternatively to running inside docker, it can sometimes be easier
to use npm directly for quicker reloading. To run using npm:

```
cd frontend
npm install
npm start
```

This should redirect you to http://localhost:3000

### Frontend Tests

```
cd frontend
npm install
npm test
```

## Migrations

Migrations are run using Django's migration framework. To run all migrations:

```
docker-compose run --rm backend python manage.py migrate
```

To create a new migration after changing the models:

```
docker-compose run --rm backend python manage.py makemigrations
```

For more information see
[Django's migrations documentation](https://docs.djangoproject.com/en/stable/topics/migrations/).

## Testing

There is a helper script for both frontend and backend tests:

```
./scripts/test.sh
```

### Backend Tests

```
docker-compose run backend pytest
```

any arguments to pytest can also be passed after this command

### Frontend Tests

```
docker-compose run frontend test
```

This is the same as running npm test from within the frontend directory

## Logging

```
docker-compose logs
```

Or for a specific service:

```
docker-compose logs -f name_of_service # frontend|backend|db
```

## Project Layout

```
backend
├── app
│   ├── core        # security & celery config
│   ├── users       # user model, serializers, views
│   │   └── migrations # where migrations are located
│   ├── tests       # pytest
│   ├── settings.py # configuration
│   ├── urls.py     # root URLconf
│   └── wsgi.py     # entrypoint to backend
└── manage.py       # Django management CLI

frontend
└── public
└── src
    ├── components
    │   └── Home.tsx
    ├── config
    │   └── index.tsx   # constants
    ├── __tests__
    │   └── test_home.tsx
    ├── index.tsx   # entrypoint
    └── App.tsx     # handles routing
```
