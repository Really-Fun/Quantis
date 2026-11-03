// Медиатека: Любимое, История и аккаунт Яндекс Музыки; каждое — своя страница.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

StackView {
    id: stack
    initialItem: root

    function openAccount() {
        if (stack.depth === 1)
            stack.push(accountPage)
    }
    function openLiked() {
        if (stack.depth === 1)
            stack.push(likedPage)
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
            Rectangle {
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

    Item {
        id: root
        ColumnLayout {
            anchors.fill: parent
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
                iconName: "user"
                caption: "Яндекс Музыка"
                hint: app.loggedIn ? (app.account || "Вход выполнен") : "Не выполнен вход"
                hintColor: app.loggedIn ? theme.textDim : theme.yandex
                onClicked: stack.push(accountPage)
            }
            Item { Layout.fillHeight: true }
        }
    }
}
