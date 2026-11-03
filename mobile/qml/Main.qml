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

    // Отступы от выреза и системных панелей Android (edge-to-edge).
    readonly property real safeTop: SafeArea.margins.top
    readonly property real safeBottom: SafeArea.margins.bottom

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
            LibraryPage { id: libraryPage }
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

    PlayerSheet {
        id: player
        width: window.width
        height: window.height
        topPadding: window.safeTop
        bottomPadding: window.safeBottom
    }

    // «Назад» на Android: сначала свернуть плеер, потом на главную.
    onClosing: function (close) {
        if (player.opened) {
            close.accepted = false
            player.close()
        } else if (window.tab !== 0) {
            close.accepted = false
            window.tab = 0
        }
    }
}
