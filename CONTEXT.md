# MewBook

Desktop app that manages a personal library of ebooks and documents: it catalogues files with metadata, classifies them, and keeps track of what has been sent to e-reader devices.

## Language

### Library and removal

**Thư viện** (Library):
The set of Sách the user sees and searches in the app. A removed Sách appears only in its Tình trạng file filter, nowhere else.
_Avoid_: Kho, database

**Sách** (Book):
One catalogued entry: its metadata plus, usually, a pointer to a physical file.
_Avoid_: Tài liệu, document, bản ghi

**Xóa khỏi thư viện** (Remove from library):
Moves a Sách into the Thùng rác with the deletion kind "Xóa khỏi thư viện". The physical file stays exactly where it is.
_Avoid_: Xóa sách, delete

**Xóa file** (Delete file):
Moves a Sách into the Thùng rác with the deletion kind "Xóa file và thư viện", and moves its physical file into the Thư mục thùng rác. When the entry expires the file is deleted for good.
_Avoid_: Xóa vĩnh viễn

**Thùng rác** (Trash):
The list of every removed Sách, shown under Tình trạng file. Each entry has a deletion kind and the file's current path, which the user can click to open the file. Every entry expires after the same number of days; expiry deletes the Sách for good, and also the file when the kind is Xóa file.
_Avoid_: Recycle Bin, Sách đã xóa, File đã xóa

**Thư mục thùng rác** (Trash folder):
The folder chosen in settings (for example `D:\Thùng rác`) that receives the physical files of Xóa file.

**Tình trạng file** (File status):
The filter group that contains the Thùng rác, the only place a removed Sách is shown.

### Classification and grouping

**Tag / Hashtag**:
A label attribute attached to a Sách.

**Chưa chắc** (Unsure):
A value of the tag attribute meaning automatic classification could not place the Sách with confidence. It is replaced when a real tag is applied.
_Avoid_: Unknown, chưa phân loại

**Bộ sưu tập** (Collection):
A "virtual" group whose members the user adds by hand; it never changes the files and has no filter rules. When its name equals a Tag/Hashtag, the app only marks the two as linked; membership is never derived from the tag.
_Avoid_: Thư mục, folder

### E-reader

**Thiết bị** (Device):
An e-reader the user names and registers. A plugged-in drive is matched to a registered Thiết bị by volume label or serial; an unrecognised one is offered for registration. The Thư viện records which Sách were sent to which Thiết bị and whether each is still on it, and never writes to a Thiết bị except to copy a book file onto it.
_Avoid_: Máy, ổ đĩa
