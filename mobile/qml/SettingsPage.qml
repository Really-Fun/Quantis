// Настройки: разделы «Вид», «Поиск», «Аккаунт», «О приложении».
// Новая настройка — блок в своём разделе (или новый SectionLabel + блок)
// и свойство с сеттером в backend.py, хранящееся в QSettings.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    signal back()
    signal openAccount()

    // Подзаголовок раздела — как в медиатеке.
    component SectionLabel: Text {
        Layout.topMargin: 14
        color: theme.textDim
        font.family: theme.ui
        font.pixelSize: 13
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.8
    }

    // Строка-переход: значок, название, подпись, стрелка.
    component LinkRow: ItemDelegate {
        id: row
        property string iconName
        property string caption
        property string hint
        property color hintColor: theme.textDim
        Layout.fillWidth: true
        height: 72
        Accessible.name: caption + (hint ? ", " + hint : "")
        background: Rectangle {
            radius: theme.radius
            color: row.down ? theme.surfaceHigh : theme.surface
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
                    source: "icons/" + row.iconName + ".svg"
                    sourceSize: Qt.size(22, 22)
                    Accessible.ignored: true
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: row.caption
                    color: theme.text
                    font.family: theme.ui
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: row.hint
                    color: row.hintColor
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

    RowLayout {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 8
        anchors.leftMargin: theme.gutter - 12
        IconButton { iconName: "chevron-left"; label: "Назад"; onClicked: page.back() }
        Text {
            text: "Настройки"
            color: theme.text
            font.family: theme.display
            font.pixelSize: 20
            font.weight: Font.DemiBold
        }
    }

    Flickable {
        id: scroller
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        contentWidth: width
        contentHeight: column.implicitHeight + 32
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollIndicator.vertical: ScrollIndicator {}

        ColumnLayout {
            id: column
            x: theme.gutter
            width: scroller.width - 2 * theme.gutter
            spacing: 10

            // --- Вид ---------------------------------------------------------
            SectionLabel { text: "Вид"; Layout.topMargin: 4 }
            OnboardingCard {
                title: "Живой"
                subtitle: "Аврора и вращение пластинки"
                iconName: "music"
                tone: theme.accentPink
                selected: app.motion
                onClicked: app.setMotion(true)
            }
            OnboardingCard {
                title: "Спокойный"
                subtitle: "Без анимации, бережёт батарею"
                iconName: "moon"
                tone: theme.accentCyan
                selected: !app.motion
                onClicked: app.setMotion(false)
            }

            // --- Поиск -------------------------------------------------------
            SectionLabel { text: "Где искать" }
            OnboardingCard {
                title: "Яндекс Музыка"
                subtitle: app.loggedIn ? "Треки, альбомы, исполнители" : "Нужен вход в аккаунт"
                letter: "Я"
                tone: theme.yandex
                enabled: app.loggedIn
                selected: app.source === "yandex"
                onClicked: app.setSource("yandex")
            }
            OnboardingCard {
                title: "YouTube"
                subtitle: "Всё, что есть на YouTube Music"
                iconName: "play"
                tone: theme.youtube
                selected: app.source === "youtube"
                onClicked: app.setSource("youtube")
            }
            OnboardingCard {
                title: "SoundCloud"
                subtitle: "Ремиксы, сеты и андерграунд"
                letter: "S"
                tone: theme.soundcloud
                selected: app.source === "soundcloud"
                onClicked: app.setSource("soundcloud")
            }

            // --- Аккаунт -----------------------------------------------------
            SectionLabel { text: "Аккаунт" }
            LinkRow {
                iconName: "user"
                caption: "Яндекс Музыка"
                hint: app.loggedIn ? (app.account || "Вход выполнен") : "Не выполнен вход"
                hintColor: app.loggedIn ? theme.textDim : theme.yandex
                onClicked: page.openAccount()
            }

            // --- О приложении ------------------------------------------------
            SectionLabel { text: "О приложении" }
            LinkRow {
                iconName: "radio"
                caption: "Показать приветствие"
                hint: "Пройти первые шаги заново"
                onClicked: app.showOnboarding()
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 6
                text: "Quantis Mobile · бета"
                color: theme.textDim
                horizontalAlignment: Text.AlignHCenter
                font.family: theme.ui
                font.pixelSize: 13
            }
        }
    }
}
