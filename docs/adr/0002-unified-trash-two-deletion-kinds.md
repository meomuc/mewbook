# One Thùng rác with two deletion kinds

- **Status:** accepted (spec: `.scratch/unified-trash/spec.md`; not yet implemented).

Removing a Sách from the Thư viện used to mean two unrelated things in the code: the "Xóa khỏi thư viện" button moved the physical file into the app's trash, while the duplicate finder hard-deleted the record. We decided there is **one Thùng rác** and **two deletion kinds** recorded on the removed Sách: *Xóa khỏi thư viện* (the record is kept, the file is never touched) and *Xóa file và thư viện* (the record is kept and the file moves to the Thư mục thùng rác). Both kinds are restorable and both expire after the same number of days; expiry deletes the record permanently, plus the file for the second kind. Every removal path in the app uses exactly these two options.

## Considered options

- **Two separate lists** ("Sách đã xóa" and "File đã xóa"): rejected. The user would have to know which list to look in, and the expiry rules could drift apart.
- **Hard-delete the record on "Xóa khỏi thư viện"**: rejected. It loses hashtags, authors and looked-up metadata that the user typed or paid network calls for, and makes a mistaken removal unrecoverable.
- **Use the Windows Recycle Bin for files**: rejected. The app needs the original path and a restore that never overwrites, and the user wants to choose the folder.

## Consequences

- A removed file's path stays in the do-not-reimport list **permanently**, even after expiry; otherwise the folder watcher would silently bring a deleted book back as a new Sách with all its data gone. Restoring removes the path from that list.
- "Xóa khỏi thư viện" keeps the file in a watched folder, so the exclusion list is what keeps it out of the library, not the file's absence.
- Books trashed under the old behaviour are migrated to the kind *Xóa file và thư viện*, because their files are in the trash folder. The change is an appended column only (no rename, no drop), per the migration rules in `CLAUDE.md`.
- Reversing this later means another data migration: the deletion kind is stored per record.
