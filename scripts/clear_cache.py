from flask_caching import Cache

from app import create_app

app = create_app()
cache = Cache()


def main():
    cache.init_app(app)

    with app.app_context():
        cache.clear()


if __name__ == "__main__":
    main()
