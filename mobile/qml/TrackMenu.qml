// Меню «⋮» у трека: сыграть следующим, в конец очереди, в любимое, скачать.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

Menu {
    id: menu
    objectName: "trackMenu"
    property string listName
    property int trackIndex: -1
    // app.liked.count — зависимость: пересчитать после лайка где угодно.
    readonly property bool liked: app.liked.count >= 0 && trackIndex >= 0
                                  && app.isLikedFrom(listName, trackIndex)

    // 0 — не скачан, 1 — качается, 2 — скачан; пересчёт при открытии меню.
    property int downloadState: 0
    onAboutToShow: downloadState = app.downloadStateFrom(listName, trackIndex)

    Material.background: theme.surfaceHigh
    background: Rectangle {
        implicitWidth: 248
        radius: 14
        color: theme.surfaceHigh
        border.color: theme.stroke
    }

    MenuItem {
        text: "Играть следующим"
        icon.source: "icons/play-next.svg"
        onTriggered: app.playNextFrom(menu.listName, menu.trackIndex)
    }
    MenuItem {
        text: "В конец очереди"
        icon.source: "icons/list-plus.svg"
        visible: menu.listName !== "queue"
        height: visible ? implicitHeight : 0
        onTriggered: app.enqueueFrom(menu.listName, menu.trackIndex)
    }
    MenuItem {
        text: menu.liked ? "Убрать из любимого" : "В любимое"
        icon.source: menu.liked ? "icons/heart-filled.svg" : "icons/heart.svg"
        icon.color: menu.liked ? theme.accentPink : theme.text
        onTriggered: app.toggleLikeFrom(menu.listName, menu.trackIndex)
    }
    Menu {
        id: toPlaylist
        title: "В плейлист"
        icon.source: "icons/list-music.svg"
        background: Rectangle { implicitWidth: 248; radius: 14; color: theme.surfaceHigh; border.color: theme.stroke }
        Instantiator {
            model: app.localPlaylists
            delegate: MenuItem {
                required property var modelData
                text: modelData.name
                onTriggered: app.addToPlaylistFrom(menu.listName, menu.trackIndex, modelData.id)
            }
            onObjectAdded: function (index, object) { toPlaylist.insertItem(index, object) }
            onObjectRemoved: function (index, object) { toPlaylist.removeItem(object) }
        }
        MenuItem {
            text: "Новый плейлист…"
            icon.source: "icons/list-plus.svg"
            onTriggered: playlistDialog.openCreate(menu.listName, menu.trackIndex)
        }
    }
    MenuItem {
        text: "Убрать из плейлиста"
        icon.source: "icons/x.svg"
        visible: menu.listName === "playlist"
        height: visible ? implicitHeight : 0
        onTriggered: app.removeFromPlaylist(menu.trackIndex)
    }
    MenuItem {
        text: menu.downloadState === 2 ? "Удалить с телефона"
            : menu.downloadState === 1 ? "Скачивается…" : "Скачать"
        enabled: menu.downloadState !== 1
        icon.source: menu.downloadState === 2 ? "icons/trash.svg" : "icons/download.svg"
        onTriggered: menu.downloadState === 2
            ? app.removeDownloadFrom(menu.listName, menu.trackIndex)
            : app.downloadFrom(menu.listName, menu.trackIndex)
    }
}
