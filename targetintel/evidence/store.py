"""Immutable DuckDB storage for finalized evidence-layer contracts.

The store deliberately has no update API.  DuckDB is the operational source
of truth; Parquet files produced here are read-only snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable

import duckdb

from .models import CANONICALIZATION_VERSION, EvidenceItem, RetrievalAttempt
from .validation import (
    SemanticValidationContext,
    require_finalizable,
    require_valid_retrieval_attempt,
)


SCHEMA_VERSION = "evidence-store-v0.2.0"
SNAPSHOT_TABLES = (
    "evidence_items", "provenance_steps", "derived_links", "evidence_revisions",
    "retrieval_attempts", "ingest_audit_events",
)
ITEM_COLUMNS = tuple(
    field for field in EvidenceItem.__dataclass_fields__
    if field not in {"derived_from", "provenance_history"}
)
ATTEMPT_COLUMNS = tuple(RetrievalAttempt.__dataclass_fields__)


class StorageIntegrityError(RuntimeError):
    """A non-retryable immutable-storage integrity violation."""


class ImmutableEvidenceError(StorageIntegrityError):
    """An operation attempted to replace a stored immutable evidence item."""


class HashCollisionError(StorageIntegrityError):
    """A hash was associated with different canonical content bytes."""


@dataclass(frozen=True)
class InsertResult:
    evidence_id: str
    inserted: bool
    duplicate: bool


@dataclass(frozen=True)
class SnapshotVerification:
    table_rows: dict[str, int]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceStore:
    """A small, connection-owning immutable evidence store.

    A store instance owns one DuckDB connection and should be closed (or used
    as a context manager).  No connection is shared globally.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
        clock: Callable[[], datetime] = _utc_now,
        logical_store_id: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.read_only = read_only
        self._clock = clock
        if logical_store_id is not None and (not isinstance(logical_store_id, str) or not logical_store_id.strip()):
            raise ValueError("logical_store_id must be a non-empty string when provided")
        # This is an operator-supplied logical identity, deliberately distinct
        # from the local path.  It is optional for existing evidence-layer
        # callers, but reviewed-evidence persistence requires it explicitly.
        self.logical_store_id = logical_store_id
        if read_only:
            if not self.path.exists():
                raise FileNotFoundError(f"evidence store does not exist: {self.path}")
            if not self.path.is_file():
                raise IsADirectoryError(f"evidence store path must be a DuckDB file: {self.path}")
            try:
                self._connection = duckdb.connect(str(self.path), read_only=True)
            except duckdb.Error as exc:
                raise StorageIntegrityError(
                    f"cannot open evidence store read-only: {self.path}"
                ) from exc
            try:
                self._validate_read_only_schema()
            except Exception:
                self.close()
                raise
        else:
            self._connection = duckdb.connect(str(self.path))
            self._initialize_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "EvidenceStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        # The JSON columns preserve every contract field byte-for-byte after
        # model serialization; normalized columns make the required dimensions
        # and relations efficiently queryable.
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS evidence_items (
              evidence_id VARCHAR PRIMARY KEY, target_symbol VARCHAR NOT NULL,
              target_id VARCHAR, disease_name VARCHAR NOT NULL, disease_id VARCHAR NOT NULL,
              treatment_name VARCHAR, treatment_id VARCHAR, evidence_type VARCHAR NOT NULL,
              evidence_direction VARCHAR NOT NULL, observation TEXT NOT NULL,
              interpretation TEXT, source VARCHAR NOT NULL, source_id VARCHAR NOT NULL,
              document_location VARCHAR, quoted_span TEXT, computed_support TEXT,
              publication_id VARCHAR, source_dataset_id VARCHAR, patient_cohort_id VARCHAR,
              experiment_id VARCHAR, comparison TEXT, endpoint TEXT, data_modality VARCHAR,
              species VARCHAR NOT NULL, model_system VARCHAR NOT NULL, sample_context TEXT,
              effect_size DOUBLE, effect_size_metric VARCHAR, uncertainty DOUBLE,
              uncertainty_metric VARCHAR, sample_size INTEGER, extraction_method VARCHAR NOT NULL,
              extraction_confidence DOUBLE, validation_status VARCHAR NOT NULL,
              retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, data_release VARCHAR,
              evidence_family VARCHAR, evidence_family_algorithm_version VARCHAR NOT NULL,
              evidence_family_basis VARCHAR NOT NULL, independence_eligible BOOLEAN NOT NULL,
              independence_ineligibility_reason TEXT, record_hash VARCHAR NOT NULL UNIQUE,
              canonical_json TEXT NOT NULL, item_json TEXT NOT NULL
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_attempts (
              retrieval_attempt_id VARCHAR PRIMARY KEY, target_identifier VARCHAR NOT NULL,
              disease_context VARCHAR NOT NULL, treatment_context VARCHAR, source VARCHAR NOT NULL,
              query TEXT NOT NULL, timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
              status VARCHAR NOT NULL, result_count INTEGER, error_category VARCHAR,
              source_release_or_api_version VARCHAR, attempt_json TEXT NOT NULL
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS provenance_steps (
              evidence_id VARCHAR NOT NULL REFERENCES evidence_items(evidence_id),
              step_index INTEGER NOT NULL, step_name VARCHAR NOT NULL,
              timestamp TIMESTAMP WITH TIME ZONE NOT NULL, metadata_json TEXT NOT NULL,
              is_operational BOOLEAN NOT NULL, PRIMARY KEY (evidence_id, step_index)
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS derived_links (
              child_id VARCHAR NOT NULL REFERENCES evidence_items(evidence_id),
              parent_id VARCHAR NOT NULL REFERENCES evidence_items(evidence_id),
              PRIMARY KEY (child_id, parent_id)
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS evidence_revisions (
              newer_evidence_id VARCHAR NOT NULL REFERENCES evidence_items(evidence_id),
              prior_evidence_id VARCHAR NOT NULL REFERENCES evidence_items(evidence_id),
              reason VARCHAR NOT NULL, PRIMARY KEY (newer_evidence_id, prior_evidence_id)
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS ingest_audit_events (
              event_id VARCHAR PRIMARY KEY, timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
              event_type VARCHAR NOT NULL, submitted_hash VARCHAR, evidence_id VARCHAR,
              retrieval_attempt_id VARCHAR, details_json TEXT NOT NULL
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_metadata (
              schema_version VARCHAR PRIMARY KEY, canonicalization_version VARCHAR NOT NULL,
              updated_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
        """)
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence_items(target_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence_items(source, source_id)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_status ON evidence_items(validation_status)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_family ON evidence_items(evidence_family)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_experiment ON evidence_items(experiment_id)",
            "CREATE INDEX IF NOT EXISTS idx_retrieval_target ON retrieval_attempts(target_identifier)",
        ):
            self._connection.execute(statement)
        existing = self._connection.execute(
            "SELECT canonicalization_version FROM schema_metadata WHERE schema_version = ?", [SCHEMA_VERSION]
        ).fetchone()
        if existing is None:
            self._connection.execute(
                "INSERT INTO schema_metadata VALUES (?, ?, ?)",
                [SCHEMA_VERSION, CANONICALIZATION_VERSION, self._clock()],
            )
        elif existing[0] != CANONICALIZATION_VERSION:
            raise StorageIntegrityError("canonicalization version does not match existing store")

    def _validate_read_only_schema(self) -> None:
        """Confirm the known store contract without issuing any DDL or DML."""
        expected_columns = {
            "evidence_items": set(ITEM_COLUMNS) | {"canonical_json", "item_json"},
            "retrieval_attempts": set(ATTEMPT_COLUMNS) | {"attempt_json"},
            "provenance_steps": {"evidence_id", "step_index", "step_name", "timestamp", "metadata_json", "is_operational"},
            "derived_links": {"child_id", "parent_id"},
            "evidence_revisions": {"newer_evidence_id", "prior_evidence_id", "reason"},
            "ingest_audit_events": {"event_id", "timestamp", "event_type", "submitted_hash", "evidence_id", "retrieval_attempt_id", "details_json"},
            "schema_metadata": {"schema_version", "canonicalization_version", "updated_at"},
        }
        try:
            rows = self._connection.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'main'"
            ).fetchall()
            actual: dict[str, set[str]] = {}
            for table_name, column_name in rows:
                actual.setdefault(table_name, set()).add(column_name)
            for table_name, columns in expected_columns.items():
                if table_name not in actual:
                    raise StorageIntegrityError(f"evidence store schema is missing table: {table_name}")
                missing = columns - actual[table_name]
                if missing:
                    raise StorageIntegrityError(
                        f"evidence store schema is missing columns in {table_name}: {', '.join(sorted(missing))}"
                    )
            metadata = self._connection.execute(
                "SELECT schema_version, canonicalization_version FROM schema_metadata"
            ).fetchall()
        except duckdb.Error as exc:
            raise StorageIntegrityError("evidence store schema cannot be read") from exc
        expected = (SCHEMA_VERSION, CANONICALIZATION_VERSION)
        if metadata != [expected]:
            raise StorageIntegrityError(
                "evidence store schema or canonicalization version is incompatible"
            )

    def _require_writable(self) -> None:
        if self.read_only:
            raise StorageIntegrityError("evidence store is read-only; write operations are not permitted")

    def _event_id(self) -> str:
        number = self._connection.execute("SELECT count(*) FROM ingest_audit_events").fetchone()[0] + 1
        return f"audit-{number:020d}"

    def _audit(self, event_type: str, *, submitted_hash: str | None = None,
               evidence_id: str | None = None, retrieval_attempt_id: str | None = None,
               details: dict[str, object] | None = None) -> None:
        self._require_writable()
        self._connection.execute(
            "INSERT INTO ingest_audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [self._event_id(), self._clock(), event_type, submitted_hash, evidence_id,
             retrieval_attempt_id, json.dumps(details or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)],
        )

    def _items_context(self) -> SemanticValidationContext:
        rows = self._connection.execute("SELECT item_json FROM evidence_items ORDER BY evidence_id").fetchall()
        items = [EvidenceItem.from_dict(json.loads(row[0])) for row in rows]
        return SemanticValidationContext({item.evidence_id: item for item in items})

    def get_item(self, evidence_id: str) -> EvidenceItem | None:
        row = self._connection.execute("SELECT item_json FROM evidence_items WHERE evidence_id = ?", [evidence_id]).fetchone()
        return None if row is None else EvidenceItem.from_dict(json.loads(row[0]))

    def list_items(self, *, target_symbol: str | None = None) -> list[EvidenceItem]:
        if target_symbol is None:
            rows = self._connection.execute("SELECT item_json FROM evidence_items ORDER BY evidence_id").fetchall()
        else:
            rows = self._connection.execute("SELECT item_json FROM evidence_items WHERE target_symbol = ? ORDER BY evidence_id", [target_symbol]).fetchall()
        return [EvidenceItem.from_dict(json.loads(row[0])) for row in rows]

    def insert_finalized_item(self, item: EvidenceItem) -> InsertResult:
        self._require_writable()
        context = self._items_context()
        require_finalizable(item, context)
        calculated_hash = item.calculate_record_hash(context)
        if item.record_hash is None:
            raise StorageIntegrityError("record_hash must be calculated before canonical insertion")
        if item.record_hash != calculated_hash:
            raise StorageIntegrityError("record_hash does not match canonical content")
        canonical = item.canonical_json()
        duplicate = self._connection.execute("SELECT evidence_id, canonical_json FROM evidence_items WHERE record_hash = ?", [item.record_hash]).fetchone()
        if duplicate is not None:
            if duplicate[1] != canonical:
                self._record_collision(item.record_hash, duplicate[0])
                raise HashCollisionError("record hash collision with distinct canonical bytes")
            self._connection.execute("BEGIN")
            try:
                self._audit("exact_duplicate", submitted_hash=item.record_hash, evidence_id=duplicate[0],
                            details={"submitted_evidence_id": item.evidence_id})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            return InsertResult(duplicate[0], False, True)
        existing_id = self._connection.execute("SELECT record_hash FROM evidence_items WHERE evidence_id = ?", [item.evidence_id]).fetchone()
        if existing_id is not None:
            self._connection.execute("BEGIN")
            try:
                self._audit("rejected_mutation", submitted_hash=item.record_hash, evidence_id=item.evidence_id,
                            details={"reason": "evidence_id already exists"})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            raise ImmutableEvidenceError("evidence_id already exists; create a new immutable revision")
        self._connection.execute("BEGIN")
        try:
            values = item.to_dict()
            columns = list(ITEM_COLUMNS)
            # Contract list/provenance fields are preserved in item_json and normalized separately.
            columns.extend(["canonical_json", "item_json"])
            placeholders = ", ".join("?" for _ in columns)
            self._connection.execute(
                f"INSERT INTO evidence_items ({', '.join(columns)}) VALUES ({placeholders})",
                [values[name] for name in ITEM_COLUMNS] + [canonical, json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)],
            )
            for index, step in enumerate(item.provenance_history):
                self._connection.execute("INSERT INTO provenance_steps VALUES (?, ?, ?, ?, ?, ?)", [
                    item.evidence_id, index, step.step_type, step.recorded_at,
                    json.dumps(dict(step.details), sort_keys=True, separators=(",", ":"), ensure_ascii=False), step.is_operational,
                ])
            for parent in item.derived_from:
                self._connection.execute("INSERT INTO derived_links VALUES (?, ?)", [item.evidence_id, parent])
            self._audit("insertion", submitted_hash=item.record_hash, evidence_id=item.evidence_id)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return InsertResult(item.evidence_id, True, False)

    def _record_collision(self, submitted_hash: str, existing_evidence_id: str) -> None:
        self._require_writable()
        # The failed canonical transaction is complete before this independent,
        # append-only integrity audit is recorded.
        self._connection.execute("BEGIN")
        try:
            self._audit("collision", submitted_hash=submitted_hash, evidence_id=existing_evidence_id)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def link_revision(self, newer_evidence_id: str, prior_evidence_id: str, reason: str) -> None:
        self._require_writable()
        if not reason.strip():
            raise ValueError("revision reason must be non-empty")
        self._connection.execute("BEGIN")
        try:
            self._connection.execute("INSERT INTO evidence_revisions VALUES (?, ?, ?)", [newer_evidence_id, prior_evidence_id, reason])
            self._audit("revision", evidence_id=newer_evidence_id, details={"prior_evidence_id": prior_evidence_id, "reason": reason})
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def revisions_for(self, evidence_id: str) -> list[tuple[str, str, str]]:
        return [tuple(row) for row in self._connection.execute(
            "SELECT newer_evidence_id, prior_evidence_id, reason FROM evidence_revisions WHERE newer_evidence_id = ? OR prior_evidence_id = ? ORDER BY newer_evidence_id, prior_evidence_id", [evidence_id, evidence_id]
        ).fetchall()]

    def record_retrieval_attempt(self, attempt: RetrievalAttempt) -> None:
        self._require_writable()
        require_valid_retrieval_attempt(attempt)
        values = attempt.to_dict()
        self._connection.execute("BEGIN")
        try:
            existing = self._connection.execute("SELECT 1 FROM retrieval_attempts WHERE retrieval_attempt_id = ?", [attempt.retrieval_attempt_id]).fetchone()
            if existing is not None:
                raise ImmutableEvidenceError("retrieval_attempt_id already exists")
            columns = list(ATTEMPT_COLUMNS) + ["attempt_json"]
            self._connection.execute(
                f"INSERT INTO retrieval_attempts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [values[name] for name in ATTEMPT_COLUMNS] + [json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)],
            )
            self._audit("retrieval_attempt", retrieval_attempt_id=attempt.retrieval_attempt_id,
                        details={"status": attempt.status})
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def get_retrieval_attempt(self, retrieval_attempt_id: str) -> RetrievalAttempt | None:
        row = self._connection.execute("SELECT attempt_json FROM retrieval_attempts WHERE retrieval_attempt_id = ?", [retrieval_attempt_id]).fetchone()
        return None if row is None else RetrievalAttempt.from_dict(json.loads(row[0]))

    def list_retrieval_attempts(self, *, target_identifier: str | None = None, status: str | None = None) -> list[RetrievalAttempt]:
        clauses: list[str] = []
        params: list[str] = []
        if target_identifier is not None:
            clauses.append("target_identifier = ?"); params.append(target_identifier)
        if status is not None:
            clauses.append("status = ?"); params.append(status)
        where = "" if not clauses else " WHERE " + " AND ".join(clauses)
        rows = self._connection.execute("SELECT attempt_json FROM retrieval_attempts" + where + " ORDER BY timestamp, retrieval_attempt_id", params).fetchall()
        return [RetrievalAttempt.from_dict(json.loads(row[0])) for row in rows]

    def audit_events(self) -> list[dict[str, object]]:
        rows = self._connection.execute("SELECT event_id, timestamp, event_type, submitted_hash, evidence_id, retrieval_attempt_id, details_json FROM ingest_audit_events ORDER BY event_id").fetchall()
        return [{"event_id": row[0], "timestamp": row[1], "event_type": row[2], "submitted_hash": row[3], "evidence_id": row[4], "retrieval_attempt_id": row[5], "details": json.loads(row[6])} for row in rows]

    def export_snapshot(self, output_path: str | Path) -> Path:
        self._require_writable()
        output = Path(output_path)
        if output.exists():
            raise FileExistsError(f"snapshot path already exists: {output}")
        output.mkdir(parents=True)
        self._connection.execute("BEGIN")
        try:
            # An export is an operational storage event.  Record it before
            # writing the snapshot so the exported audit table is itself a
            # complete append-only account of that snapshot's creation.
            self._audit("export", details={"snapshot_path": str(output)})
            for table in SNAPSHOT_TABLES:
                destination = output / f"{table}.parquet"
                self._connection.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO ? (FORMAT PARQUET)", [str(destination)])
            manifest = {"schema_version": SCHEMA_VERSION, "canonicalization_version": CANONICALIZATION_VERSION, "tables": list(SNAPSHOT_TABLES)}
            (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            # An incomplete export must not masquerade as an immutable snapshot.
            for child in output.iterdir():
                child.unlink()
            output.rmdir()
            raise
        return output

    @staticmethod
    def verify_snapshot(snapshot_path: str | Path) -> SnapshotVerification:
        """Read a snapshot into an isolated in-memory DuckDB without mutation."""
        path = Path(snapshot_path)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("canonicalization_version") != CANONICALIZATION_VERSION:
            raise StorageIntegrityError("snapshot schema metadata does not match this store")
        connection = duckdb.connect(":memory:", read_only=False)
        try:
            counts = {table: connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path / f"{table}.parquet")]).fetchone()[0] for table in SNAPSHOT_TABLES}
            evidence_rows = connection.execute(
                "SELECT item_json, canonical_json FROM read_parquet(?) ORDER BY evidence_id",
                [str(path / "evidence_items.parquet")],
            ).fetchall()
            items = [EvidenceItem.from_dict(json.loads(row[0])) for row in evidence_rows]
            context = SemanticValidationContext({item.evidence_id: item for item in items})
            for item, row in zip(items, evidence_rows):
                require_finalizable(item, context)
                if item.record_hash != item.calculate_record_hash(context) or row[1] != item.canonical_json():
                    raise StorageIntegrityError("snapshot evidence content does not match its canonical hash")
            attempts = connection.execute(
                "SELECT attempt_json FROM read_parquet(?) ORDER BY retrieval_attempt_id",
                [str(path / "retrieval_attempts.parquet")],
            ).fetchall()
            for row in attempts:
                require_valid_retrieval_attempt(RetrievalAttempt.from_dict(json.loads(row[0])))
        finally:
            connection.close()
        return SnapshotVerification(counts)
