// Главная. Шаг 1: приветствие, «Продолжить» с играющим треком и вход в поиск.
// «Моя волна», недавнее и любимое — шаги 3–4.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Flickable {
    id: page
    signal searchRequested()
    signal playerRequested()

    contentHeight: column.implicitHeight + 32
    clip: true
    boundsBehavior: Flickable.DragOverBounds

    function greeting() {
        var hour = new Date().getHours()
        if (hour < 5) return "Доброй ночи"
        if (hour < 12) return "Доброе утро"
        if (hour < 18) return "Добрый день"
        return "Добрый вечер"
    }

    // Подсветка верха страницы цветами играющего трека — та же аврора, что в
    // плеере, только тише; без трека её нет.
    Aurora {
        width: page.width
        height: 420
        y: -page.contentY * 0.4 // лёгкий параллакс при прокрутке
        visible: app.hasTrack
        opacity: 0.8
        active: app.playing && !app.loading
    }

    ColumnLayout {
        id: column
        width: page.width
        spacing: 20

        Text {
            Layout.leftMargin: theme.gutter
            Layout.topMargin: 20
            text: page.greeting()
            color: theme.text
            font.family: theme.display
            font.pixelSize: 26
            font.weight: Font.DemiBold
        }

        // Главная карточка: играющий трек или приглашение к поиску.
        Rectangle {
            id: hero
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.preferredHeight: 176
            radius: theme.radius + 4
            // Без трека — фирменный градиент; с треком — тёмное стекло поверх авроры.
            gradient: app.hasTrack ? null : brand
            color: app.hasTrack ? Qt.rgba(0.08, 0.09, 0.12, 0.55) : "transparent"
            border.color: app.hasTrack ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
            Gradient {
                id: brand
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.darker(theme.accent, 1.6) }
                GradientStop { position: 1; color: Qt.darker(theme.accentPink, 2.4) }
            }

            // Обложка с пластинкой справа, пока что-то играет.
            Item {
                id: heroArt
                visible: app.hasTrack
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                width: 132
                height: 104
                Vinyl {
                    x: 36; y: 2
                    width: 100; height: 100
                    cover: app.cover
                    spinning: app.playing && !app.loading
                }
                CoverArt {
                    width: 104; height: 104
                    radius: 14
                    seed: app.title
                    cover: app.cover
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                anchors.rightMargin: app.hasTrack ? heroArt.width + 28 : 20
                spacing: 6
                Text {
                    text: app.hasTrack ? "СЕЙЧАС ИГРАЕТ" : "QUANTIS"
                    color: Qt.rgba(1, 1, 1, 0.7)
                    font.family: theme.ui
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    font.letterSpacing: 1.6
                }
                Text {
                    Layout.fillWidth: true
                    text: app.hasTrack ? app.title : "Яндекс Музыка и YouTube в одном плеере"
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: app.hasTrack
                    text: app.artist
                    color: Qt.rgba(1, 1, 1, 0.75)
                    font.family: theme.ui
                    font.pixelSize: 14
                    elide: Text.ElideRight
                }
                Item { Layout.fillHeight: true }
                PillButton {
                    text: app.hasTrack ? "Открыть плеер" : "Найти музыку"
                    variant: "light"
                    onClicked: app.hasTrack ? page.playerRequested() : page.searchRequested()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            text: app.loggedIn
                  ? "Вход в Яндекс Музыку выполнен. Ищи треки во вкладке «Поиск»."
                  : "Войди в Яндекс Музыку в «Медиатеке», чтобы искать там. YouTube работает и без входа."
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }
    }
}
