from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:40] or "alert"


def normalize_alertmanager_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a Prometheus Alertmanager webhook group into a RootSignal workflow."""
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        raise ValueError("Alertmanager payload must contain at least one alert")
    if len(alerts) > 100:
        raise ValueError("Alertmanager payload cannot contain more than 100 alerts")
    if any(not isinstance(alert, dict) for alert in alerts):
        raise ValueError("Each Alertmanager alert must be an object")

    common_labels = _mapping(payload.get("commonLabels"))
    common_annotations = _mapping(payload.get("commonAnnotations"))
    first_alert = alerts[0]
    assert isinstance(first_alert, dict)
    first_labels = _mapping(first_alert.get("labels"))
    first_annotations = _mapping(first_alert.get("annotations"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    alert_name = str(common_labels.get("alertname") or first_labels.get("alertname") or "alert")
    title = str(common_annotations.get("summary") or first_annotations.get("summary") or alert_name)
    summary = str(
        common_annotations.get("description")
        or first_annotations.get("description")
        or f"Alertmanager reported {len(alerts)} alert(s) for {alert_name}"
    )

    log_rows: list[str] = []
    deployment_rows: list[str] = []
    firing = 0
    resolved = 0
    for alert in alerts:
        labels = _mapping(alert.get("labels"))
        annotations = _mapping(alert.get("annotations"))
        status = str(alert.get("status", "unknown"))
        firing += status == "firing"
        resolved += status == "resolved"
        log_rows.append(json.dumps({
            "status": status,
            "labels": labels,
            "annotations": annotations,
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
            "generator_url": alert.get("generatorURL"),
            "fingerprint": alert.get("fingerprint"),
        }, sort_keys=True))
        deployment = next(
            (
                labels[key]
                for key in ("deployment", "version", "revision", "release")
                if key in labels
            ),
            None,
        )
        if deployment is not None:
            deployment_rows.append(f"{labels.get('service', 'service')} deployment {deployment}")

    log_rows.append(json.dumps({
        "receiver": payload.get("receiver"),
        "group_labels": _mapping(payload.get("groupLabels")),
        "common_labels": common_labels,
        "common_annotations": common_annotations,
        "external_url": payload.get("externalURL"),
    }, sort_keys=True))
    if not deployment_rows:
        deployment_rows.append("Deployment context was not supplied by Alertmanager")

    return {
        "workflow_id": f"alertmanager-{digest[:24]}",
        "query": f"Investigate this Alertmanager event: {summary}",
        "intake": {
            "id": f"alertmanager-{_slug(alert_name)}-{digest[:12]}",
            "title": title,
            "summary": summary,
            "failure_class": "alertmanager-alert",
            "telemetry": {
                "metrics": {
                    "alert_count": len(alerts),
                    "firing_alerts": firing,
                    "resolved_alerts": resolved,
                },
                "logs": log_rows,
                "deployments": sorted(set(deployment_rows)),
            },
        },
    }
