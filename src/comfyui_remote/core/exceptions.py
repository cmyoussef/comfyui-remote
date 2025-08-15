"""Errors."""
class ComfyRemoteError(Exception): pass
class ValidationError(ComfyRemoteError): pass
class ConnectorError(ComfyRemoteError): pass
class ServerNotReady(ComfyRemoteError): pass
class SubmissionError(ComfyRemoteError): pass
