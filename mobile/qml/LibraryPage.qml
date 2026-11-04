// Медиатека: Любимое, История, медиатека Яндекса («Мне нравится» и свои
// плейлисты, если выполнен вход) и аккаунт; каждое — своя страница.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

StackView {
    id: stack
    initialItem: root
    // Вкладку открыли — медиатеку Яндекса обновить (не чаще раза в 5 минут).
    onVisibleChanged: if (visible && app.loggedIn) app.refreshYandexLibrary()

    function openAccount() {
        if (stack.depth === 1)
            stack.push(accountPage)
    }
    function openLiked() {
        if (stack.depth === 1)
            stack.push(likedPage)
    }
    function openYandexLiked() {
        if (stack.depth === 1)
            stack.push(yandexLikedPage)
    }

    Component {
        id: accountPage
        AccountPage { onBack: stack.pop() }
    }
    Component {
        id: likedPage
        TrackListPage {
            title: "Любимое"
            listName: "liked"
            model: app.liked
            emptyText: "Нажми «♡» в плеере или в меню трека — он появится здесь"
            onBack: stack.pop()
        }
    }
    Component {
        id: yandexLikedPage
        TrackListPage {
            title: "Мне нравится"
            listName: "yandexLiked"
            model: app.yandexLiked
            loading: app.yandexLibraryLoading
            emptyText: "В «Мне нравится» на Яндексе пока пусто"
            onBack: stack.pop()
        }
    }
    Component {
        id: playlistPage
        TrackListPage {
            listName: "remote"
            model: app.remote
            loading: app.remoteLoading
            errorText: app.remoteError
            emptyText: "В плейлисте нет доступных треков"
            onBack: stack.pop()
        }
    }
    function openPlaylist(item) {
        if (stack.depth !== 1)
            return
        app.openPlaylist(item.uid, item.kind)
        stack.push(playlistPage, { title: item.title })
    }
    Component {
        id: downloadedPage
        TrackListPage {
            title: "Скачанное"
            listName: "downloaded"
            model: app.downloaded
            emptyText: "Скачай трек в меню «⋮» или весь список кнопкой со стрелкой — он будет играть без сети"
            onBack: stack.pop()
        }
    }
    Component {
        id: historyPage
        TrackListPage {
            title: "История"
            listName: "history"
            model: app.history
            emptyText: "Здесь будет то, что ты слушал"
            onBack: stack.pop()
        }
    }

    // Строка медиатеки: значок, название, подпись, стрелка.
    component LibraryRow: ItemDelegate {
        id: entry
        property string iconName
        property string caption
        property string hint
        property color hintColor: theme.textDim
        property string cover: "" // url-encoded https — обложка вместо значка
        Layout.fillWidth: true
        Layout.leftMargin: theme.gutter - 4
        Layout.rightMargin: theme.gutter - 4
        height: 72
        Accessible.name: caption
        background: Rectangle {
            radius: theme.radius
            color: entry.down ? theme.surfaceHigh : theme.surface
            Behavior on color { ColorAnimation { duration: theme.fast } }
        }
        contentItem: RowLayout {
            spacing: 14
            CoverArt {
                visible: entry.cover !== ""
                Layout.preferredWidth: 44; Layout.preferredHeight: 44
                seed: entry.caption
                cover: entry.cover
            }
            Rectangle {
                visible: entry.cover === ""
                Layout.preferredWidth: 44; Layout.preferredHeight: 44
                radius: 22
                color: theme.surfaceHigh
                Image {
                    anchors.centerIn: parent
                    source: "icons/" + entry.iconName + ".svg"
                    sourceSize: Qt.size(22, 22)
                    Accessible.ignored: true
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: entry.caption
                    color: theme.text
                    font.family: theme.ui
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    text: entry.hint
                    color: entry.hintColor
                    font.family: theme.ui
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
            Image {
                source: "icons/chevron-right.svg"
                sourceSize: Qt.size(20, 20)
                opacity: 0.5
                Accessible.ignored: true
            }
        }
    }

    function tracksLabel(n) {
        var tail = n % 10, tens = n % 100
        var word = (tail === 1 && tens !== 11) ? "трек"
                 : (tail >= 2 && tail <= 4 && (tens < 12 || tens > 14)) ? "трека" : "треков"
        return n + " " + word
    }

    // Подзаголовок раздела.
    component SectionLabel: Text {
        Layout.leftMargin: theme.gutter
        Layout.topMargin: 14
        color: theme.textDim
        font.family: theme.ui
        font.pixelSize: 13
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.8
    }

    Flickable {
        id: root
        contentHeight: column.implicitHeight + 24
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollIndicator.vertical: ScrollIndicator {}
        ColumnLayout {
            id: column
            width: root.width
            spacing: 10

            Text {
                Layout.leftMargin: theme.gutter
                Layout.topMargin: 20
                Layout.bottomMargin: 4
                text: "Медиатека"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 26
                font.weight: Font.DemiBold
            }
            LibraryRow {
                iconName: "heart"
                caption: "Любимое"
                hint: stack.tracksLabel(app.liked.count)
                onClicked: stack.push(likedPage)
            }
            LibraryRow {
                iconName: "list-music"
                caption: "История"
                hint: stack.tracksLabel(app.history.count)
                onClicked: stack.push(historyPage)
            }
            LibraryRow {
                iconName: "download"
                caption: "Скачанное"
                hint: app.downloadsPending > 0
                    ? "Скачиваем: " + app.downloadingTitle + " · осталось " + app.downloadsPending
                    : stack.tracksLabel(app.downloaded.count)
                      + (app.downloaded.count > 0 ? " · " + app.offlineSize : "")
                onClicked: stack.push(downloadedPage)
            }
            SectionLabel {
                visible: app.loggedIn
                text: "Яндекс Музыка"
            }
            LibraryRow {
                visible: app.loggedIn
                iconName: "heart-filled"
                caption: "Мне нравится"
                hint: app.yandexLiked.count > 0 ? stack.tracksLabel(app.yandexLiked.count)
                    : (app.yandexLibraryLoading ? "Загружаем…" : "Пусто")
                onClicked: stack.openYandexLiked()
            }
            Repeater {
                model: app.loggedIn ? app.yandexPlaylists : []
                LibraryRow {
                    required property var modelData
                    iconName: "list-music"
                    caption: modelData.title
                    hint: stack.tracksLabel(modelData.count)
                    cover: modelData.cover ? encodeURIComponent(modelData.cover) : ""
                    onClicked: stack.openPlaylist(modelData)
                }
            }
            SectionLabel { text: "Аккаунт" }
            LibraryRow {
                iconName: "user"
                caption: "Яндекс Музыка"
                hint: app.loggedIn ? (app.account || "Вход выполнен") : "Не выполнен вход"
                hintColor: app.loggedIn ? theme.textDim : theme.yandex
                onClicked: stack.push(accountPage)
            }
        }
    }
}
