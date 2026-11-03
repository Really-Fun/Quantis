// Очередь: что играет и что дальше. Касание — сыграть с этого трека.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Drawer {
    id: sheet
    edge: Qt.BottomEdge
    interactive: opened
    dragMargin: 0
    modal: true
    // Тёмное затемнение под шторкой: у Material по умолчанию светлое.
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.55) }

    background: Rectangle {
        color: theme.surface
        radius: 24
        Rectangle { // нижние углы — прямые
            anchors.bottom: parent.bottom
            width: parent.width; height: 24
            color: parent.color
        }
    }

    onOpened: list.positionViewAtIndex(Math.max(0, app.queueIndex), ListView.Beginning)

    ColumnLayout {
        anchors.fill: parent
        anchors.bottomMargin: sheet.bottomPadding
        spacing: 0

        Rectangle { // ручка шторки
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 10
            width: 36; height: 4; radius: 2
            color: theme.stroke
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: 4
            Layout.topMargin: 8
            ColumnLayout {
                spacing: 2
                Text {
                    text: "Очередь"
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
                Text {
                    text: !app.waveActive ? app.queue.count + " в очереди"
                          : app.waveName === "Моя волна" ? "Моя волна" : "Моя волна · " + app.waveName
                    color: theme.textDim
                    font.family: theme.ui
                    font.pixelSize: 13
                }
            }
            Item { Layout.fillWidth: true }
            IconButton { iconName: "x"; label: "Закрыть очередь"; onClicked: sheet.close() }
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 8
            clip: true
            model: app.queue
            delegate: TrackRow {
                listName: "queue"
                current: index === app.queueIndex
                opacity: index < app.queueIndex ? 0.5 : 1 // уже сыгранные — тише
            }
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
}
