// Каркас: вкладки, мини-плеер, нижняя панель и полноэкранный плеер.
// Контроллер приложения — объект «app» (backend.py).
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 412
    height: 892
    visible: true
    title: "Quantis"
    color: theme.bg

    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.primary: theme.accent
    Material.background: theme.bg
    Material.foreground: theme.text
    font.family: theme.ui
    font.pixelSize: 16

    Theme { id: theme }

    property int tab: 0

    // Окно python-for-android уже начинается под строкой состояния и
    // кончается над панелью навигации, а SafeArea.margins всё равно сообщает
    // их высоту: с ними отступ получался двойным (чёрные полосы сверху и
    // снизу на телефоне). Поэтому своих отступов не добавляем.
    readonly property real safeTop: 0
    readonly property real safeBottom: 0

    Item {
        anchors.fill: parent
        anchors.topMargin: window.safeTop
        anchors.bottomMargin: window.safeBottom

        StackLayout {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: mini.visible ? mini.top : nav.top
            anchors.bottomMargin: mini.visible ? 8 : 0
            currentIndex: window.tab
            HomePage {
                onSearchRequested: function (query) {
                    window.tab = 1
                    if (query.length > 0)
                        searchPage.runQuery(query)
                }
                onPlayerRequested: player.open()
                onAccountRequested: {
                    window.tab = 2
                    libraryPage.openAccount()
                }
            }
            SearchPage { id: searchPage }
            LibraryPage { id: libraryPage; objectName: "libraryPage" }
        }

        MiniPlayer {
            id: mini
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: nav.top
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            anchors.bottomMargin: 8
            visible: app.hasTrack
            onOpen: player.open()
        }

        BottomNav {
            id: nav
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            current: window.tab
            onSelected: function (index) { window.tab = index }
        }
    }

    QueueSheet {
        id: queueSheet
        objectName: "queueSheet"
        z: 1 // открывается поверх плеера
        width: window.width
        height: window.height * 0.72
        bottomPadding: window.safeBottom
    }

    LyricsSheet {
        id: lyricsSheet
        objectName: "lyricsSheet"
        z: 1
        width: window.width
        height: window.height * 0.86
        bottomPadding: window.safeBottom
    }

    PlayerSheet {
        id: player
        objectName: "playerSheet"
        width: window.width
        height: window.height
        topPadding: window.safeTop
        bottomPadding: window.safeBottom
    }

    // «Назад» на Android: сначала свернуть плеер, потом на главную.
    onClosing: function (close) {
        if (lyricsSheet.opened) {
            close.accepted = false
            lyricsSheet.close()
        } else if (queueSheet.opened) {
            close.accepted = false
            queueSheet.close()
        } else if (player.opened) {
            close.accepted = false
            player.close()
        } else if (window.tab !== 0) {
            close.accepted = false
            window.tab = 0
        }
    }
}
