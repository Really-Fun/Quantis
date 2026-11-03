// Поиск: поле, выбор источника, выдача. Пустое состояние и ошибки — текстом
// под полем, загрузка — индикатором.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: page

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Text {
            Layout.leftMargin: theme.gutter
            Layout.topMargin: 20
            text: "Поиск"
            color: theme.text
            font.family: theme.display
            font.pixelSize: 26
            font.weight: Font.DemiBold
        }

        TextField {
            id: query
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 16
            placeholderText: "Трек, артист или альбом"
            font.family: theme.ui
            font.pixelSize: 16
            leftPadding: 44
            rightPadding: 16
            topPadding: 14
            bottomPadding: 14
            inputMethodHints: Qt.ImhNoPredictiveText
            color: theme.text
            placeholderTextColor: theme.textDim
            background: Rectangle {
                radius: theme.radius
                color: theme.surface
                border.color: query.activeFocus ? theme.accent : theme.stroke
                border.width: query.activeFocus ? 2 : 1
                Behavior on border.color { ColorAnimation { duration: theme.fast } }
            }
            onAccepted: app.search(text)
            Accessible.name: "Поиск музыки"
            Image {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20
                source: "icons/search.svg"
                sourceSize: Qt.size(20, 20)
                opacity: 0.6
                Accessible.ignored: true
            }
        }

        RowLayout {
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 12
            spacing: 8
            Repeater {
                model: [{ id: "yandex", label: "Яндекс Музыка" }, { id: "youtube", label: "YouTube" }]
                delegate: PillButton {
                    required property var modelData
                    text: modelData.label
                    variant: app.source === modelData.id ? "filled" : "outlined"
                    compact: true
                    Accessible.checked: app.source === modelData.id
                    onClicked: {
                        app.setSource(modelData.id)
                        if (query.text.trim().length > 0 && app.source === modelData.id)
                            app.search(query.text)
                    }
                }
            }
            Item { Layout.fillWidth: true }
        }

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 8
            visible: text.length > 0
            text: app.status
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 8

            ListView {
                id: list
                anchors.fill: parent
                clip: true
                model: app.results
                boundsBehavior: Flickable.DragOverBounds
                delegate: TrackRow {
                    current: app.hasTrack && title === app.title && artist === app.artist
                    onClicked: app.playResult(index)
                }
                ScrollIndicator.vertical: ScrollIndicator {}
            }

            BusyIndicator {
                anchors.centerIn: parent
                running: app.searching
                visible: running
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 2 * theme.gutter
                visible: !app.searching && list.count === 0 && app.status.length === 0
                spacing: 8
                Image {
                    Layout.alignment: Qt.AlignHCenter
                    source: "icons/search.svg"
                    sourceSize: Qt.size(40, 40)
                    opacity: 0.35
                    Accessible.ignored: true
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: app.source === "yandex"
                          ? "Ищи по названию или артисту в Яндекс Музыке"
                          : "Ищи по названию или артисту на YouTube"
                    color: theme.textDim
                    wrapMode: Text.WordWrap
                    font.family: theme.ui
                    font.pixelSize: 15
                }
            }
        }
    }
}
