""""Lưu thành bộ sưu tập": keep the filter you just built as a Virtual Collection.

Filters that fit a collection's rule list (see domain/filter_collections.py)
become a self-updating collection -- new books that match join it. Anything
more tangled (a search text, two groups with several values each) is saved as
the *current* documents instead, and the prompt says so before it happens.
"""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.domain.filter_collections import rules_from_filter
from smartdoc.domain.library_filter import COLLECTIONS, LibraryFilter, describe
from smartdoc.domain.smart_collections import VirtualCollection


def save_filter_as_collection(context, flt: LibraryFilter, parent: QWidget | None = None) -> str | None:
    """Ask for a name and create the collection; returns its id (or None if cancelled)."""
    names = {row["id"]: row["name"] for row in context.db.list_collections()}
    converted = rules_from_filter(flt)
    if converted is not None:
        note = "Bộ sưu tập sẽ tự cập nhật: sách mới khớp điều kiện sẽ tự vào."
    else:
        note = "Điều kiện này quá phức tạp để tự cập nhật, nên sẽ lưu cố định các tài liệu đang hiển thị."
    default = describe(flt, names, limit=2).replace("; ", " · ")
    name, accepted = QInputDialog.getText(parent, "Lưu thành bộ sưu tập", f"{note}\n\nTên bộ sưu tập:", text=default)
    name = name.strip()
    if not accepted or not name:
        return None
    if name.casefold() in {existing.casefold() for existing in names.values()}:
        QMessageBox.warning(parent, "Bộ sưu tập đã tồn tại", f"Đã có bộ sưu tập tên \"{name}\". Vui lòng chọn tên khác.")
        return None

    if converted is not None:
        rules, logic = converted
        collection = VirtualCollection(name=name, rules=rules, logic=logic)
        context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)
    else:
        collection = VirtualCollection(name=name)
        context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)
        where_sql, params = context.db.filter_where(flt)
        doc_ids = context.db.list_document_ids_matching(fts_query=flt.query, where_sql=where_sql, params=params)
        context.db.add_documents_to_collection(collection.id, doc_ids)

    context.event_bus.publish(LibraryUpdatedEvent())
    context.filters.set(LibraryFilter().with_values(COLLECTIONS, (collection.id,)))
    return collection.id
