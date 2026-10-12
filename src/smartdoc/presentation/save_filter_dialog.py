""""Lưu thành bộ sưu tập": keep the books a filter shows right now as a collection.

A collection is only the books put in it, so this keeps the *current* documents of the filter (search text and all);
books that match the filter later do not join by themselves.
"""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.domain.library_filter import COLLECTIONS, LibraryFilter, describe
from smartdoc.domain.smart_collections import VirtualCollection


def save_filter_as_collection(context, flt: LibraryFilter, parent: QWidget | None = None) -> str | None:
    """Ask for a name and create the collection; returns its id (or None if cancelled)."""
    names = {row["id"]: row["name"] for row in context.db.list_collections()}
    note = "Bộ sưu tập sẽ lưu cố định các sách đang hiển thị; sách thêm sau này không tự vào."
    default = describe(flt, names, limit=2).replace("; ", " · ")
    name, accepted = QInputDialog.getText(parent, "Lưu thành bộ sưu tập", f"{note}\n\nTên bộ sưu tập:", text=default)
    name = name.strip()
    if not accepted or not name:
        return None
    if name.casefold() in {existing.casefold() for existing in names.values()}:
        QMessageBox.warning(parent, "Bộ sưu tập đã tồn tại", f"Đã có bộ sưu tập tên \"{name}\". Vui lòng chọn tên khác.")
        return None

    collection = VirtualCollection(name=name)
    context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)
    where_sql, params = context.db.filter_where(flt)
    doc_ids = context.db.list_document_ids_matching(fts_query=flt.query, where_sql=where_sql, params=params)
    context.db.add_documents_to_collection(collection.id, doc_ids)

    context.event_bus.publish(LibraryUpdatedEvent())
    context.filters.set(LibraryFilter().with_values(COLLECTIONS, (collection.id,)))
    return collection.id
