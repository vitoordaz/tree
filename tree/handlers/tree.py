import asyncio
import json

from aiohttp import web

import bson
import bson.errors


def int_or_zero(v):
  try:
    return int(v)
  except (TypeError, ValueError):
    return 0


def error_body(errors):
  return bytes(json.dumps({'errors': errors}), encoding='utf-8')


class TreeHandler(object):

  @staticmethod
  @asyncio.coroutine
  def insert(request):
    # Make sure that request is valid first.
    data = yield from request.json()
    if not data.get('text'):  # text is required field.
      raise web.HTTPBadRequest(body=error_body({'text': 'Required'}))

    db = request.app['db']

    # Make sure that parent exist if it's given.
    parent_id = data.get('parent_id') or None
    if not parent_id:
      parent = None
    else:
      try:
        parent_id = bson.ObjectId(parent_id)
      except (TypeError, bson.errors.InvalidId):
        raise web.HTTPBadRequest(body=error_body({'parent_id': 'Invalid id'}))
      parent = yield from db.tree.find_one({'_id': parent_id})
      if not parent:
        raise web.HTTPBadRequest(body=error_body({'parent_id': 'Not found'}))

    node = {'_id': bson.ObjectId(), 'text': data['text']}
    node['path'] = '/%(_id)s' % node
    if parent:
      node['parent'] = bson.DBRef('tree', parent['_id'])
      node['path'] = '%s%s' % (parent['path'], node['path'])
    node_id = yield from db.tree.insert(node)

    return web.HTTPCreated(body=bytes(json.dumps({'id': str(node_id)}),
                                      encoding='utf-8'))

  @staticmethod
  @asyncio.coroutine
  def _send_items(cursor, limit=10, offset=0):
    try:
      total = yield from cursor.count()
      cursor.skip(offset)
      cursor.limit(limit)
      items = []
      while (yield from cursor.fetch_next):
        node = cursor.next_object()
        items.append({
            'id': str(node['_id']),
            'text': node['text'],
            'path': node['path']
        })
    finally:
      cursor.close()
    return web.HTTPOk(body=bytes(json.dumps({
        'meta': {'total': total, 'limit': limit, 'offset': offset},
        'items': items
    }), encoding='utf-8'))

  @staticmethod
  @asyncio.coroutine
  def query(request):
    search = request.GET.get('search')
    limit = min(int_or_zero(request.GET.get('limit')) or 10, 10)
    offset = int_or_zero(request.GET.get('offset'))
    db = request.app['db']
    query = {}
    if search:
      query['$text'] = {'$search': search}
    cursor = db.tree.find(query).sort('path')
    response = yield from TreeHandler._send_items(cursor, limit, offset)
    return response

  @staticmethod
  @asyncio.coroutine
  def get_by_id(request):
    limit = min(int_or_zero(request.GET.get('limit')) or 10, 10)
    offset = int_or_zero(request.GET.get('offset'))

    node_id = request.match_info['id']
    try:
      node_id = bson.ObjectId(node_id)
    except (TypeError, bson.errors.InvalidId):
      raise web.HTTPNotFound()

    db = request.app['db']

    node = yield from db.tree.find_one({'_id': node_id})
    if not node:
      raise web.HTTPNotFound()

    cursor = db.tree.find({'path': {
        '$regex': '^%(path)s' % node
    }}).sort('path')
    response = yield from TreeHandler._send_items(cursor, limit, offset)
    return response
