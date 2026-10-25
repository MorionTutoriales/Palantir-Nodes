"""Librería «MediaPipe»: manos, cuerpo y rostros."""

from palantir_nodes.libraries import LibraryInfo, Requirement
from palantir_nodes.libraries.mediapipe_lib.nodes import (
    FaceDetection,
    FaceMesh,
    HandLandmarks,
    LandmarkPoint,
    PoseLandmarks,
)

LIBRARY = LibraryInfo(
    id="mediapipe",
    label="MediaPipe",
    description=(
        "Detección de manos, cuerpo y rostros con MediaPipe. Cada detector dibuja los puntos "
        "sobre la imagen y entrega su cantidad, los puntos y las cajas; «Landmark Point» saca "
        "un punto concreto (p. ej. la punta del índice) como coordenadas. La primera vez cada "
        "detector descarga su modelo oficial (necesita Internet) y lo guarda en "
        "~/.palantir_nodes/models; también puedes indicar tu propio archivo de modelo."
    ),
    nodes=(HandLandmarks, PoseLandmarks, FaceMesh, FaceDetection, LandmarkPoint),
    requirements=(Requirement("mediapipe", "mediapipe"),),
)
