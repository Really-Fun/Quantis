// Страница со списком треков (Любимое, История, «Мне нравится», плейлист):
// назад, заголовок, список; для загружаемых — индикатор и текст ошибки.
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
    property bool loading: false
    property string errorText: ""
    property string actionText: "" // доп. кнопка в шапке (пусто — нет)
    signal back()
    signal action()

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
                visible: page.actionText !== ""
                text: page.actionText
                compact: true
                onClicked: page.action()
            }
            IconButton {
                visible: list.count > 0 && page.listName !== "downloaded"
                iconName: "download"
                label: "Скачать все"
                onClicked: app.downloadAll(page.listName)
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

            BusyIndicator {
                anchors.centerIn: parent
                running: page.loading && list.count === 0
                visible: running
            }
            Text {
                anchors.centerIn: parent
                width: parent.width - 2 * theme.gutter
                visible: list.count === 0 && !page.loading
                horizontalAlignment: Text.AlignHCenter
                text: page.errorText || page.emptyText
                color: theme.textDim
                wrapMode: Text.WordWrap
                font.family: theme.ui
                font.pixelSize: 15
            }
        }
    }
}
