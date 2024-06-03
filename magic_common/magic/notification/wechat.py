import threading

import requests

from magic.config import config


def send_wx_markdown_message(message):
    url = config.MAGIC_WX_ERROR_URL
    if not url:
        return
    resp = requests.post(url, json={
        'msgtype': 'markdown',
        'markdown': {
            'content': message
        }
    })
    return resp


def async_send_wx_markdown_message(message):
    threading.Thread(
        target=send_wx_markdown_message,
        args=(message, ),
    ).start()
