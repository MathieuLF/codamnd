from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import ErrorDetail, FileOperationError, ValidationFailed
from .models import EmployeurDEntry


SOURCE_LINE_LENGTH = 77
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_LINES = 100_000
MAX_VALIDATION_ERRORS = 100
AMOUNT_PATTERN = re.compile(r"^-?\d+(?:\.\d{1,2})?$")
CENT = Decimal("0.01")


def parse_employeurd_file(path: Path, *, reject_non_crlf: bool = False, encoding: str = "ascii") -> list[EmployeurDEntry]:
    return parse_employeurd_bytes(
        read_employeurd_bytes(path),
        reject_non_crlf=reject_non_crlf,
        encoding=encoding,
    )


def read_employeurd_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_SOURCE_BYTES + 1)
        if len(content) > MAX_SOURCE_BYTES:
            raise ValidationFailed(f"Le fichier source dépasse la limite de {MAX_SOURCE_BYTES // (1024 * 1024)} Mo.")
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le fichier source: {path}") from error
    return content


def parse_employeurd_bytes(
    content: bytes,
    *,
    reject_non_crlf: bool = False,
    encoding: str = "ascii",
) -> list[EmployeurDEntry]:

    if not content:
        raise ValidationFailed("Le fichier source est vide.")

    raw_lines = _split_lines(content, reject_non_crlf=reject_non_crlf, max_lines=MAX_SOURCE_LINES)
    entries: list[EmployeurDEntry] = []
    errors: list[ErrorDetail] = []

    for line_number, raw_line in enumerate(raw_lines, start=1):
        if raw_line == b"":
            errors.append(ErrorDetail("source_empty_line", "Ligne vide interdite.", line_number))
        else:
            try:
                line = raw_line.decode(encoding)
            except UnicodeDecodeError:
                errors.append(ErrorDetail("source_encoding", f"Ligne non décodable en {encoding}.", line_number))
            else:
                try:
                    entries.append(parse_employeurd_line(line, line_number))
                except ValidationFailed as error:
                    errors.extend(error.errors)
        if len(errors) >= MAX_VALIDATION_ERRORS:
            errors = errors[:MAX_VALIDATION_ERRORS]
            errors.append(
                ErrorDetail(
                    "source_too_many_errors",
                    f"Validation interrompue après {MAX_VALIDATION_ERRORS} erreurs.",
                )
            )
            break

    if errors:
        raise ValidationFailed(errors)
    if not entries:
        raise ValidationFailed("Le fichier source ne contient aucune écriture.")
    return entries


def parse_employeurd_line(line: str, line_number: int = 1) -> EmployeurDEntry:
    errors: list[ErrorDetail] = []

    if len(line) != SOURCE_LINE_LENGTH:
        errors.append(
            ErrorDetail(
                "source_line_length",
                f"Longueur attendue {SOURCE_LINE_LENGTH}, reçue {len(line)}.",
                line_number,
            )
        )
        raise ValidationFailed(errors)

    batch = line[0:8]
    separator = line[8:9]
    account = line[9:20]
    amount_text = line[20:69].strip()
    date_text = line[69:77]

    if not batch.isdigit():
        errors.append(ErrorDetail("source_batch", "Le lot doit contenir 8 chiffres.", line_number, "batch"))
    if separator != " ":
        errors.append(ErrorDetail("source_separator", "Un espace est obligatoire après le lot.", line_number))
    if len(account) != 11 or not account.isdigit():
        errors.append(ErrorDetail("source_account", "Le compte source doit contenir 11 chiffres.", line_number, "account"))

    amount = Decimal("0")
    if not amount_text:
        errors.append(ErrorDetail("source_amount_empty", "Le montant est obligatoire.", line_number, "amount"))
    elif not AMOUNT_PATTERN.fullmatch(amount_text):
        errors.append(
            ErrorDetail("source_amount_format", "Le montant doit être signé avec au plus 2 décimales.", line_number, "amount")
        )
    else:
        try:
            amount = Decimal(amount_text)
        except InvalidOperation:
            errors.append(ErrorDetail("source_amount_decimal", "Le montant n'est pas un nombre décimal valide.", line_number, "amount"))
        else:
            if amount != amount.quantize(CENT):
                errors.append(ErrorDetail("source_amount_scale", "Le montant ne doit pas dépasser 2 décimales.", line_number))

    entry_date = None
    if len(date_text) != 8 or not date_text.isdigit():
        errors.append(ErrorDetail("source_date_format", "La date doit être AAAAMMJJ.", line_number, "date"))
    else:
        try:
            entry_date = datetime.strptime(date_text, "%Y%m%d").date()
        except ValueError:
            errors.append(ErrorDetail("source_date_invalid", "La date est invalide.", line_number, "date"))

    if errors:
        raise ValidationFailed(errors)

    assert entry_date is not None
    return EmployeurDEntry(
        line_number=line_number,
        batch=batch,
        account=account,
        amount=amount,
        entry_date=entry_date,
        raw_line=line,
    )


def _split_lines(content: bytes, *, reject_non_crlf: bool, max_lines: int) -> list[bytes]:
    if reject_non_crlf:
        normalized = content.replace(b"\r\n", b"")
        if b"\r" in normalized or b"\n" in normalized:
            raise ValidationFailed("Les fins de ligne source doivent être CRLF en mode strict.")

    if b"\r\n" in content:
        separator = b"\r\n"
    elif b"\n" in content:
        separator = b"\n"
    elif b"\r" in content:
        separator = b"\r"
    else:
        separator = None
    line_count = content.count(separator) + (0 if content.endswith(separator) else 1) if separator else 1
    if line_count > max_lines:
        raise ValidationFailed(f"Le fichier source dépasse la limite de {max_lines} lignes.")

    lines = content.split(separator) if separator else [content]

    if lines and lines[-1] == b"":
        lines = lines[:-1]
    return lines
