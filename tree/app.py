import asyncio
import logging

from aiohttp import web
from motor import motor_asyncio
import pymongo

from .handlers import tree


logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Application(object):

  def __init__(self, config=None):
    self.config = {
        'port': 8080,
        'host': '0.0.0.0',
        'mongodb_uri': 'mongodb://localhost:27017',
        'mongodb_db': 'tree'
    }
    self.config.update(config or {})

  def _get_db(self):
    client = motor_asyncio.AsyncIOMotorClient(self.config['mongodb_uri'])
    yield from client.open()  # Make sure that we can connect to mongodb.
    db = client[self.config['mongodb_db']]
    yield from db.tree.ensure_index([
        ('text', pymongo.TEXT),
        ('path', pymongo.ASCENDING)
    ])
    return db

  @asyncio.coroutine
  def _get_app(self):
    app = web.Application()
    app['db'] = yield from self._get_db()
    app.router.add_route('POST', r'/tree', tree.TreeHandler.insert,
                         name='tree:insert')
    app.router.add_route('GET', r'/tree', tree.TreeHandler.query,
                         name='tree:query')
    app.router.add_route('GET', r'/tree/{id}', tree.TreeHandler.get_by_id,
                         name='tree:get_by_id')
    return app

  def run(self):
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(self._get_app())
    handler = app.make_handler()
    f = loop.create_server(handler, self.config['host'], self.config['port'])
    srv = loop.run_until_complete(f)
    logging.info('Serving on %s', srv.sockets[0].getsockname())
    try:
      loop.run_forever()
    except KeyboardInterrupt:
      pass
    finally:
      loop.run_until_complete(handler.finish_connections(1.0))
      srv.close()
      loop.run_until_complete(srv.wait_closed())
      loop.run_until_complete(app.finish())
    loop.close()
