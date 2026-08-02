"""Domain exceptions whose public representation never contains internals."""


class SafeRouteError(Exception):
    code = "saferoute_error"


class ConfigurationError(SafeRouteError):
    code = "configuration_error"


class PersistenceError(SafeRouteError):
    code = "persistence_error"


class RoutingUnavailableError(SafeRouteError):
    code = "routing_unavailable"
