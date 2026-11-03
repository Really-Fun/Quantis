// Страница со списком треков (Любимое, История): назад, заголовок, список.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: page
    property string title
    property string listName
    property var model
    property string emptyText
    signal back()

    ColumnLayout {
        anchors.fill: parent
        spacing: 4

        RowLayout {
            Layout.topMargin: 8
            Layout.leftMargin: 4
            IconButton { iconName: "chevron-left"; label: "Назад"; onClicked: page.back() }
            Text {
                Layout.fillWidth: true
                text: page.title
                color: theme.text
                font.family: theme.display
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            PillButton {
                visible: list.count > 0
                text: "Слушать"
                compact: true
                Layout.rightMargin: theme.gutter
                onClicked: app.playFrom(page.listName, 0)
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.model
            delegate: TrackRow {
                listName: page.listName
                current: app.hasTrack && title === app.title && artist === app.artist
            }
            ScrollIndicator.vertical: ScrollIndicator {}

            Text {
                anchors.centerIn: parent
                width: parent.width - 2 * theme.gutter
                visible: list.count === 0
                horizontalAlignment: Text.AlignHCenter
                text: page.emptyText
                color: theme.textDim
                wrapMode: Text.WordWrap
                font.family: theme.ui
                font.pixelSize: 15
            }
        }
    }
}
