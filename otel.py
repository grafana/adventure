# Import the function to set the global logger provider from the OpenTelemetry logs module.
from opentelemetry._logs import set_logger_provider

# Import the OTLPLogExporter class from the OpenTelemetry http log exporter module for exporting logs.
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

# Import LoggerProvider and LoggingHandler classes to create and handle logging with OpenTelemetry.
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler

# Import BatchLogRecordProcessor to handle batches of log records before export.
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

# Import the Resource class to associate resources such as service name and instance ID with metrics, logs, and traces.
from opentelemetry.sdk.resources import Resource

# Import the standard Python logging module to log application-specific information.
import logging

# Import metrics-related modules for managing and exporting metrics with OpenTelemetry.
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Import tracing-related modules for setting up and managing traces.
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Import exemplar-related classes from OpenTelemetry SDK
from opentelemetry.sdk.metrics import TraceBasedExemplarFilter

import os
# Interval in seconds for exporting metrics periodically.
INTERVAL_SEC = 10


class CustomTracer:
    def __init__(self, service_name):
        # Set up TracerProvider only once globally
        if os.environ.get("SETUP") == "docker":
            exporter = OTLPSpanExporter(endpoint="http://otel-collector:4318/v1/traces")
        else:
            exporter = OTLPSpanExporter()
        span_processor = BatchSpanProcessor(span_exporter=exporter)

        # Create a singleton TracerProvider if not already configured
        tracer_provider = TracerProvider(
                sampler=TraceIdRatioBased(1.0),
                resource=Resource.create(
                    {"service.name": service_name, "service.instance.id": "instance-1"}
                )
            )

        trace.set_tracer_provider(tracer_provider)
        trace.get_tracer_provider().add_span_processor(span_processor)

    def get_trace(self):
        return trace


class CustomMetrics:
    """
    CustomMetrics sets up metrics collection using OpenTelemetry with a specified service name.
    """
    def __init__(self, service_name):
        try:
            # Create the metrics exporter to send data to the backend.
            if os.environ.get("SETUP") == "docker":
                exporter = OTLPMetricExporter(endpoint="http://otel-collector:4318/v1/metrics")
            else:
                exporter = OTLPMetricExporter()

            # Set up a PeriodicExportingMetricReader to export metrics at regular intervals.
            metric_reader = PeriodicExportingMetricReader(exporter, INTERVAL_SEC)

            # Create a MeterProvider with a TraceBasedExemplarFilter to enable exemplars
            # when measurements are taken in the context of a sampled span
            self.meter_provider = MeterProvider(
                metric_readers=[metric_reader], 
                resource=Resource.create({"service.name": service_name, "service.instance.id": "instance-1"}),
                # Configure the TraceBasedExemplarFilter to add exemplars to metrics
                exemplar_filter=TraceBasedExemplarFilter()
            )

            # Set the meter provider as the global meter provider.
            metrics.set_meter_provider(self.meter_provider)

            # Obtain a meter to use in creating metrics.
            self.meter = metrics.get_meter(__name__)

            # Indicate successful metrics configuration.
            print("Metrics configured with OpenTelemetry with exemplar support enabled.")
        except Exception as e:
            # Handle errors during metrics setup and set the meter to None for safety.
            self.meter = None
            print(f"Error configuring metrics: {e}")
    
    def get_meter(self):
        """
        Return the configured meter. Raises an error if the meter isn't configured properly.
        """
        if self.meter is None:
            raise RuntimeError("Meter is not configured. Please check for errors during initialization.")
        return self.meter


class CustomLogFW:
    """
    CustomLogFW sets up logging using OpenTelemetry with a specified service name and instance ID.
    """
    def __init__(self, service_name):
        try:
            # Create an instance of LoggerProvider with a Resource object.
            # Resource is used to include metadata like the service name and instance ID.
            self.logger_provider = LoggerProvider(
                resource=Resource.create(
                    {
                        "service.name": service_name,
                        "service.instance.id": "instance-1"
                    }
                )
            )
            # Flag indicating that the logger provider is properly configured.
            self.logger_configured = True
        except Exception as e:
            # In case of error, set the logger provider to None and set the configured flag to False.
            self.logger_provider = None
            self.logger_configured = False
            print(f"Error configuring logging: {e}")

    def setup_logging(self):
        """
        Set up the logging configuration for OpenTelemetry.

        :return: A LoggingHandler instance configured with the logger provider.
        :raises: RuntimeError if the logger provider is not configured properly.
        """
        if not self.logger_configured:
            # If the logger provider wasn't set up correctly, raise an error.
            raise RuntimeError("LoggerProvider not configured correctly. Cannot set up logging.")

        # Set the created LoggerProvider as the global logger provider.
        set_logger_provider(self.logger_provider)

        # Create an instance of OTLPLogExporter to export logs.
        if os.environ.get("SETUP") == "docker":
            exporter = OTLPLogExporter(endpoint="http://otel-collector:4318/v1/logs")
            print(exporter._endpoint, flush=True)
        else:
            exporter = OTLPLogExporter()

        # Add a BatchLogRecordProcessor to the logger provider.
        # This processor batches logs before sending them to the backend.
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter=exporter, max_queue_size=5, max_export_batch_size=1)
        )

        # Create a LoggingHandler that integrates OpenTelemetry logging with the Python logging system.
        # Setting log level to NOTSET to capture all log levels.
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=self.logger_provider)

        # Indicate successful logging configuration.
        print("Logging configured with OpenTelemetry.")

        return handler
