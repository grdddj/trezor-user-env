#!/usr/bin/env python3

"""
HTTPServer used as proxy for trezord calls from the outside of docker container
This is workaround for original ip not beeing passed to the container. https://github.com/docker/for-mac/issues/180
Listening on port 21326 and routes requests to the trezord with changed Origin header
It's also serving "controller.html" at the server index: http://localhost:21326/
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import requests
from termcolor import colored
import sys

TREZORD_HOST = "0.0.0.0:21325"
HEADERS = {
    "Host": TREZORD_HOST,
    "Origin": "https://user-env.trezor.io",
}
IP = "0.0.0.0"
PORT = 21326
SERVER = None
LOG_COLOR = "green"


# POST request headers override
# origin is set to the actual machine that made the call not localhost
def merge_headers(original):
    headers = original.copy()
    headers.update(HEADERS)
    return headers


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET(body=False)

    def do_GET(self, body=True):
        try:
            # print("GET: Headers: {}".format(self.headers))
            if self.path == "/status/":
                # read trezord status page
                url = "http://{}{}".format(TREZORD_HOST, self.path)
                resp = requests.get(url)
                # print("   Resp: Headers: {}".format(resp.headers))

                self.send_response(resp.status_code)
                self.send_resp_headers(resp)
                self.wfile.write(resp.content)
            return
        except Exception as e:
            self.send_error(404, "Error trying to proxy: %s Error: %s" % (self.path, e))

    def do_POST(self, body=True):
        try:
            # print("POST Path: {}".format(self.path))
            # print("POST Headers: {}".format(self.headers))
            url = "http://{}{}".format(TREZORD_HOST, self.path)
            data_len = int(self.headers.get("content-length", 0))
            data = self.rfile.read(data_len)
            headers = merge_headers(dict(self.headers))
            # print("POST Modified headers: {}".format(headers))
            # print("POST Data: {}".format(data))

            resp = requests.post(url, data=data, headers=headers)
            # print("POST Resp Headers: {}".format(resp.headers))
            # print("POST Resp Data: {}".format(resp.content))

            self.send_response(resp.status_code)
            self.send_resp_headers(resp)
            if body:
                self.wfile.write(resp.content)
            return
        except Exception as e:
            self.send_error(404, "Error trying to proxy: %s Error: %s" % (self.path, e))

    def send_resp_headers(self, resp):
        # response Access-Control header needs to be exact with original request from the caller
        self.send_header(
            "Access-Control-Allow-Origin",
            self.headers.get("Access-Control-Allow-Origin", "*"),
        )

        # remove Access-Control and Transfer-Encoding headers from the original trezord response
        h = dict(resp.headers)
        h.pop(
            "Transfer-Encoding", "chunked"
        )  # this header returns empty response to the caller (trezor-link)
        h.pop("Access-Control-Allow-Origin", None)
        for key, value in h.items():
            self.send_header(key, value)
        self.end_headers()

    def log_message(self, format, *args):
        """Adds color to make the log clearer."""
        sys.stderr.write(
            colored(
                "BRIDGE PROXY: %s - - [%s] %s\n"
                % (self.address_string(), self.log_date_time_string(), format % args),
                LOG_COLOR,
            )
        )


class ThreadingServer(ThreadingMixIn, HTTPServer):
    pass


def start():
    print(
        colored(
            "BRIDGE PROXY: Starting at {}:{}. All requests will be forwarded to Bridge.".format(
                IP, PORT
            ),
            LOG_COLOR,
        )
    )
    global SERVER
    assert SERVER is None
    SERVER = ThreadingServer((IP, PORT), Handler)
    SERVER.daemon_threads = True
    thread = threading.Thread(target=SERVER.serve_forever)
    thread.daemon = True
    thread.start()


def stop():
    print(colored("BRIDGE PROXY: Stopping", LOG_COLOR))
    assert isinstance(SERVER, ThreadingServer)
    SERVER.shutdown()
