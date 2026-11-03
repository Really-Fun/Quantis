// Главная: логотип и аккаунт, карточка «Сейчас играет» (или «Найти музыку»),
// «Недавно играло» лентой обложек и «Недавние запросы» чипами.
// «Моя волна» — шаг 4.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Flickable {
    id: page
    signal searchRequested(string query)
    signal playerRequested()
    signal accountRequested()

    contentHeight: column.implicitHeight + 32
    clip: true
    boundsBehavior: Flickable.DragOverBounds

    // Подсветка верха страницы цветами играющего трека — та же аврора, что в
    // плеере, только тише; без трека её нет.
    Aurora {
        width: page.width
        height: 440
        y: -page.contentY * 0.4 // лёгкий параллакс при прокрутке
        visible: app.hasTrack
        opacity: 0.8
        active: app.playing && !app.loading
    }

    ColumnLayout {
        id: column
        width: page.width
        spacing: 24

        // Шапка: логотип и вход в аккаунт.
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter - 8
            Layout.topMargin: 12
            Text {
                Layout.fillWidth: true
                text: "QUANTIS"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 20
                font.weight: Font.Bold
                font.letterSpacing: 3
            }
            IconButton {
                iconName: "user"
                label: app.loggedIn ? "Аккаунт Яндекс Музыки" : "Войти в Яндекс Музыку"
                onClicked: page.accountRequested()
            }
        }

        // Главная карточка: играющий трек или приглашение к поиску.
        Rectangle {
            id: hero
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.preferredHeight: 168
            radius: theme.radius + 4
            // Без трека — фирменный градиент; с треком — тёмное стекло поверх авроры.
            gradient: app.hasTrack ? null : brand
            color: app.hasTrack ? Qt.rgba(0.08, 0.09, 0.12, 0.55) : "transparent"
            border.color: app.hasTrack ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
            Gradient {
                id: brand
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.darker(theme.accent, 1.5) }
                GradientStop { position: 1; color: Qt.darker(theme.accentPink, 2.3) }
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
                    text: app.hasTrack ? "СЕЙЧАС ИГРАЕТ" : "ЯНДЕКС МУЗЫКА · YOUTUBE"
                    color: Qt.rgba(1, 1, 1, 0.7)
                    font.family: theme.ui
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    font.letterSpacing: 1.6
                }
                Text {
                    Layout.fillWidth: true
                    text: app.hasTrack ? app.title : "Что послушаем?"
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
                    onClicked: app.hasTrack ? page.playerRequested() : page.searchRequested("")
                }
            }
        }

        // Недавно играло: лента обложек, касание — играть с этого места.
        ColumnLayout {
            Layout.fillWidth: true
            visible: app.history.count > 0
            spacing: 12
            Text {
                Layout.leftMargin: theme.gutter
                text: "Недавно играло"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 196
                orientation: ListView.Horizontal
                spacing: 12
                leftMargin: theme.gutter
                rightMargin: theme.gutter
                clip: true
                model: app.history
                boundsBehavior: Flickable.DragOverBounds
                delegate: ItemDelegate {
                    id: tile
                    required property int index
                    required property string title
                    required property string artist
                    required property string cover
                    width: 140
                    height: 196
                    padding: 0
                    Accessible.name: title + ", " + artist
                    onClicked: app.playHistory(index)
                    background: Item {}
                    contentItem: ColumnLayout {
                        spacing: 8
                        CoverArt {
                            Layout.preferredWidth: 140
                            Layout.preferredHeight: 140
                            radius: 14
                            seed: tile.title
                            cover: tile.cover
                            scale: tile.down ? 0.97 : 1
                            Behavior on scale { NumberAnimation { duration: theme.fast } }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: tile.title
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: tile.artist
                            color: theme.textDim
                            font.family: theme.ui
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // Недавние запросы: касание повторяет поиск.
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            visible: app.recentQueries.length > 0
            spacing: 12
            Text {
                text: "Недавние запросы"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: app.recentQueries
                    delegate: PillButton {
                        required property string modelData
                        text: modelData
                        variant: "outlined"
                        compact: true
                        onClicked: page.searchRequested(modelData)
                    }
                }
            }
        }

        // Первый запуск: ни истории, ни запросов.
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            visible: app.history.count === 0 && app.recentQueries.length === 0
            text: app.loggedIn
                  ? "Найди трек во вкладке «Поиск» — здесь появится то, что ты слушал."
                  : "Войди в Яндекс Музыку (значок справа вверху) или ищи на YouTube без входа."
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }
    }
}
