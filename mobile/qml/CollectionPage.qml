// Страница альбома, исполнителя, плейлиста или чарта (app.openCollection):
// обложка, название, «Слушать» и «Скачать все», треки; у исполнителя —
// «Популярные треки» и лента альбомов, касание альбома открывает его тут же.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: page
    property var collection // Collection из backend
    property string kind: "" // album | artist | playlist | chart | local | liked
    readonly property bool isArtist: kind === "artist"

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        model: page.collection ? page.collection.tracks : null
        boundsBehavior: Flickable.DragOverBounds
        ScrollIndicator.vertical: ScrollIndicator {}
        // Шапка вырастает, когда страница загрузилась: вернуться к её началу.
        Connections {
            target: page.collection
            function onChanged() { Qt.callLater(list.positionViewAtBeginning) }
        }
        delegate: TrackRow {
            listName: page.collection.listName
            current: app.hasTrack && title === app.title && artist === app.artist
        }

        header: ColumnLayout {
            width: list.width
            spacing: 0
            RowLayout {
                Layout.topMargin: 8
                Layout.leftMargin: 4
                IconButton {
                    iconName: "chevron-left"; label: "Назад"
                    onClicked: page.StackView.view.pop()
                }
                Item { Layout.fillWidth: true }
            }
            CoverArt {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 200
                Layout.preferredHeight: 200
                radius: page.isArtist ? 100 : 20
                glyph: 0.3
                seed: page.collection ? page.collection.title : ""
                cover: page.collection && page.collection.cover
                       ? encodeURIComponent(page.collection.cover) : ""
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 16
                Layout.leftMargin: theme.gutter
                Layout.rightMargin: theme.gutter
                horizontalAlignment: Text.AlignHCenter
                text: page.collection ? page.collection.title : ""
                color: theme.text
                font.family: theme.display
                font.pixelSize: 24
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                horizontalAlignment: Text.AlignHCenter
                visible: text.length > 0
                text: page.collection ? page.collection.subtitle : ""
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 14
                elide: Text.ElideRight
            }
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 16
                spacing: 8
                visible: list.count > 0
                PillButton {
                    text: "Слушать"
                    onClicked: app.playFrom(page.collection.listName, 0)
                }
                IconButton {
                    iconName: "download"
                    label: "Скачать все"
                    onClicked: app.downloadAll(page.collection.listName)
                }
            }
            Text {
                Layout.leftMargin: theme.gutter
                Layout.topMargin: 20
                Layout.bottomMargin: 4
                visible: page.isArtist && list.count > 0
                text: "Популярные треки"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 24
                running: !!page.collection && page.collection.loading
                visible: running
            }
            Text {
                Layout.fillWidth: true
                Layout.margins: theme.gutter
                visible: !!page.collection && !page.collection.loading && list.count === 0
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: page.collection && page.collection.error ? page.collection.error : "Здесь пока пусто"
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 15
            }
            Item { Layout.preferredHeight: 8 }
        }

        footer: ColumnLayout {
            width: list.width
            spacing: 0
            Item { Layout.preferredHeight: 16 }
            CoverRibbon {
                title: "Альбомы"
                model: page.collection ? page.collection.albums : []
                onPicked: function (item) { window.openPage(page.StackView.view, "album", item.id, item.title) }
            }
            Item { Layout.preferredHeight: 24 }
        }
    }
}
