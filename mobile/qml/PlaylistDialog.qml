// Диалог плейлиста: создать (и сразу добавить трек, если пришли из меню
// трека), переименовать или подтвердить удаление.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Dialog {
    id: dialog
    property string mode: "create" // create | rename | delete
    property string playlistId: ""
    property string pendingList: "" // трек, который добавить в новый плейлист
    property int pendingRow: -1
    signal deleted()

    function openCreate(listName, row) {
        mode = "create"; playlistId = ""; pendingList = listName || ""; pendingRow = row === undefined ? -1 : row
        field.text = ""; open()
    }
    function openRename(id, name) {
        mode = "rename"; playlistId = id; pendingList = ""; field.text = name; open()
    }
    function openDelete(id, name) {
        mode = "delete"; playlistId = id; pendingList = ""; field.text = name; open()
    }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(parent ? parent.width - 2 * theme.gutter : 360, 380)
    title: mode === "create" ? "Новый плейлист" : mode === "rename" ? "Переименовать" : "Удалить плейлист?"
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.55) }
    background: Rectangle { radius: 20; color: theme.surfaceHigh; border.color: theme.stroke }
    onOpened: if (mode !== "delete") field.forceActiveFocus()

    function accept_() {
        if (mode === "create") {
            var id = app.createPlaylist(field.text)
            if (pendingList !== "" && pendingRow >= 0)
                app.addToPlaylistFrom(pendingList, pendingRow, id)
        } else if (mode === "rename") {
            app.renamePlaylist(playlistId, field.text)
        } else {
            app.deletePlaylist(playlistId)
            dialog.deleted()
        }
        close()
    }

    contentItem: ColumnLayout {
        spacing: 16
        InputField {
            id: field
            visible: dialog.mode !== "delete"
            Layout.fillWidth: true
            placeholderText: "Название"
            onAccepted: dialog.accept_()
        }
        Text {
            visible: dialog.mode === "delete"
            Layout.fillWidth: true
            text: "«" + field.text + "» удалится с телефона. Скачанные треки останутся."
            wrapMode: Text.WordWrap
            color: theme.textDim
            font.family: theme.ui
            font.pixelSize: 15
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8
            PillButton { text: "Отмена"; variant: "text"; compact: true; onClicked: dialog.close() }
            PillButton {
                text: dialog.mode === "create" ? "Создать" : dialog.mode === "rename" ? "Сохранить" : "Удалить"
                compact: true
                onClicked: dialog.accept_()
            }
        }
    }
}
