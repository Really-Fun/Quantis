// Метка источника: YA, YT или SC. Цвет — дополнение к тексту, не единственный признак.
import QtQuick

Rectangle {
    property string source: ""

    visible: source.length > 0
    implicitWidth: label.implicitWidth + 10
    implicitHeight: 18
    radius: 5
    color: Qt.rgba(1, 1, 1, 0.08)
    readonly property color tone: source === "yandex" ? theme.yandex
                                : source === "soundcloud" ? theme.soundcloud : theme.youtube
    border.color: tone
    border.width: 1

    Text {
        id: label
        anchors.centerIn: parent
        text: source === "yandex" ? "YA" : source === "soundcloud" ? "SC" : "YT"
        color: parent.tone
        font.family: theme.ui
        font.pixelSize: 10
        font.weight: Font.Bold
        font.letterSpacing: 0.5
    }
    Accessible.name: source === "yandex" ? "Яндекс Музыка"
                     : source === "soundcloud" ? "SoundCloud" : "YouTube"
}
