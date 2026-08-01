import json
import socket
import ssl
import time
import urllib.error
import urllib.request

from .errors import ApiError


class Client:
    """Sends the payload assembled by PromptBuilder to the provider's API.
    One POST, one parsed response — there is no tool loop yet."""

    RETRYABLE_STATUS_CODES = [408, 409, 429, 500, 502, 503, 504]
    TRANSIENT_ERRORS = (
        EOFError,
        ConnectionResetError,
        ConnectionRefusedError,
        TimeoutError,
        ssl.SSLError,
        socket.gaierror,
        urllib.error.URLError,
    )
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 0.5
    # Ruby takes Net::HTTP's 60s open/read defaults. urlopen with no timeout
    # blocks on the global socket default, which is normally forever — so the
    # transient-error path would never fire on a hung connection.
    TIMEOUT = 60

    def __init__(self, builder):
        self.builder = builder

    def call(self, *, max_output_tokens=1024, tools=None):
        payload = self.builder.to_api_payload(
            max_output_tokens=max_output_tokens, tools=tools
        )
        request = urllib.request.Request(
            self.builder.url(),
            data=json.dumps(payload).encode(),
            headers=self.builder.headers(),
            method="POST",
        )

        attempts = 0

        while True:
            attempts += 1

            try:
                with urllib.request.urlopen(request, timeout=self.TIMEOUT) as response:
                    body = response.read().decode()
                break
            # HTTPError subclasses URLError, so it has to be caught first.
            # Reversed, every 500 would be swallowed as a transient connection
            # failure and the status-code retry list below would never run.
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read().decode()

                if self._retryable_response(status) and attempts <= self.MAX_RETRIES:
                    time.sleep(self._retry_delay(attempts))
                    continue

                raise ApiError(
                    f"API request failed after {attempts} "
                    f"attempt{'' if attempts == 1 else 's'} ({status}): {body}"
                )
            except self.TRANSIENT_ERRORS as e:
                if attempts > self.MAX_RETRIES:
                    raise ApiError(
                        f"API request failed after {attempts} attempts: "
                        f"{type(e).__name__}: {e}"
                    )

                time.sleep(self._retry_delay(attempts))
                continue

        return json.loads(body)

    # ---------- private ---------------------------------------------------

    def _retryable_response(self, status):
        return status in self.RETRYABLE_STATUS_CODES

    def _retry_delay(self, attempt):
        return self.BASE_RETRY_DELAY * (2 ** (attempt - 1))
