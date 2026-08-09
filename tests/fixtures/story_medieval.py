from __future__ import annotations

from api import server
from api.services.story_contract import STORY_CONTRACT_VERSION, StoryBrief


SPEECH = (
    "Imagine viajar comigo para uma feira da Idade Média. Naquele tempo, médicos "
    "observavam sinais do corpo com os recursos disponíveis. Hoje sabemos que a "
    "obesidade é uma doença crônica complexa. Na botica, ervas e frascos lembram "
    "como o conhecimento mudou. Evidências atuais orientam avaliação individual, "
    "alimentação adequada, atividade física e tratamento médico seguro. História "
    "ajuda a entender o caminho, mas decisões de saúde pertencem ao presente. "
    "Procure orientação profissional e não interrompa medicamentos por conta própria."
)
SPEECH_HASH = server.hash_text(SPEECH)


def medieval_brief() -> StoryBrief:
    return StoryBrief(
        storyType="historical_explainer",
        educationalGoal="Explicar um conceito médico atual por meio de uma viagem histórica responsável.",
        period="Europa medieval, século XIII",
        location="Feira pública e botica de uma vila",
        historicalAccuracy="inspired",
        tone="curious_educational",
        durationSeconds=48,
        maxHeyGenJobs=12,
        maxRegenerationsPerShot=1,
        maxBudgetUsd=50,
        characterId="doctor-main",
        lookId="look-medieval",
        characterDescription="O mesmo médico aprovado, com rosto, idade, cabelo, barba e corpo preservados.",
        wardrobeDirection="Túnica grafite, capa marrom de lã e botas de couro sem elementos modernos.",
        referenceAssets=[
            {
                "id": "reference-doctor",
                "kind": "image",
                "sha256": "a" * 64,
                "description": "Referência aprovada do personagem principal.",
            }
        ],
    )


def _shot(
    *,
    order: int,
    strategy: str,
    purpose: str,
    subject: str,
    environment: str,
    action: str,
    framing: str,
    movement: str,
    lighting: str,
    atmosphere: str,
    start: int,
    end: int,
    duration: float,
) -> dict:
    avatar = strategy == "avatar_anchor"
    return {
        "id": f"shot-{order:02d}",
        "order": order,
        "narrativePurpose": purpose,
        "shotType": "avatar_anchor" if avatar else "historical_broll",
        "strategy": strategy,
        "providerStrategy": "direct_video" if avatar else "video_agent",
        "subject": subject,
        "durationSeconds": duration,
        "speech": {
            "mode": "avatar_speaks" if avatar else "voice_continues_from_base_scene",
            "startWordIndex": start,
            "endWordIndex": end,
        },
        "character": {
            "required": avatar,
            "characterId": "doctor-main" if avatar else None,
            "lookId": "look-medieval" if avatar else None,
        },
        "environment": environment,
        "period": "Europa medieval, século XIII",
        "wardrobe": (
            "Túnica grafite, capa marrom de lã e botas de couro"
            if avatar
            else "Figurantes com tecidos naturais historicamente plausíveis"
        ),
        "action": action,
        "camera": {
            "framing": framing,
            "movement": movement,
            "lens": "perspectiva natural cinematográfica",
        },
        "lighting": lighting,
        "atmosphere": atmosphere,
        "continuityKeys": ["medieval-village-v1", "warm-documentary-v1"],
        "referenceAssetIds": ["reference-doctor"] if avatar else [],
        "negativePrompt": [
            "objetos modernos",
            "eletricidade",
            "plástico",
            "texto na imagem",
            "anatomia deformada",
        ],
        "heygenPrompt": (
            f"Photorealistic cinematic medieval Europe. {subject}. "
            f"Environment: {environment}. Action: {action}. Camera: {framing}, {movement}. "
            f"Lighting: {lighting}. Atmosphere: {atmosphere}. Natural materials only, "
            "historically plausible architecture, no electricity, plastic, modern objects, "
            "written text, logos, distorted anatomy or cartoon style."
        ),
        "audioPolicy": "preserve_base_narration" if avatar else "mute_generated_audio",
        "estimatedCost": {"heygenJobs": 1, "anthropicCalls": 0},
    }


def medieval_plan() -> dict:
    return {
        "contractVersion": STORY_CONTRACT_VERSION,
        "storyBible": {
            "premise": "Um médico atravessa um portal e usa uma vila medieval para explicar como o cuidado evoluiu.",
            "educationalGoal": medieval_brief().educationalGoal,
            "narrativeArc": {
                "opening": "Portal e chegada à vila medieval",
                "development": "Observação da feira e da botica",
                "turn": "Contraste entre recursos históricos e evidências atuais",
                "ending": "Retorno ao presente com orientação segura",
            },
            "historicalSetting": {
                "period": "Europa medieval, século XIII",
                "location": "Feira pública e botica de uma vila",
                "accuracyMode": "inspired",
            },
        },
        "characterBible": {
            "characterId": "doctor-main",
            "lookId": "look-medieval",
            "identityRule": "Preservar exatamente rosto, idade aparente, cabelo, barba e proporções corporais.",
            "voiceRule": "Usar somente a voz já aprovada para o personagem.",
            "wardrobe": {
                "base": "Túnica grafite e capa marrom de lã",
                "accessories": ["cinto de couro", "botas de couro"],
                "colors": ["grafite", "marrom", "ocre"],
            },
            "forbiddenChanges": [
                "trocar o rosto",
                "mudar cabelo ou barba",
                "adicionar acessórios modernos",
            ],
        },
        "visualBible": {
            "palette": "Tons terrosos, madeira, pedra, linho cru e luz âmbar",
            "lighting": "Luz natural quente com interiores iluminados por janelas e velas",
            "cameraStyle": "Documentário histórico cinematográfico com movimentos suaves",
            "texture": "Fotorrealista, orgânica, tátil e sem acabamento plástico",
            "forbiddenAnachronisms": [
                "eletricidade",
                "plástico",
                "asfalto",
                "embalagens industriais",
                "tipografia moderna",
            ],
        },
        "medicalAssertions": [],
        "shots": [
            _shot(
                order=1,
                strategy="cinematic_broll",
                purpose="Abrir a viagem com o portal e estabelecer a época.",
                subject="A luminous restrained portal opening beside the approved doctor as a medieval village appears",
                environment="Estrada de terra na entrada de uma vila murada",
                action="O portal se fecha enquanto a câmera revela a feira ao fundo",
                framing="plano geral vertical",
                movement="travelling suave para frente",
                lighting="amanhecer quente com névoa leve",
                atmosphere="exploratória, histórica e contida",
                start=0,
                end=9,
                duration=6,
            ),
            _shot(
                order=2,
                strategy="avatar_anchor",
                purpose="Apresentar o personagem falando dentro da feira.",
                subject="The approved doctor speaking directly to camera in a busy medieval market",
                environment="Feira medieval com barracas de madeira, tecidos e cerâmica",
                action="O médico explica com gestos naturais enquanto pessoas passam ao fundo",
                framing="plano médio",
                movement="aproximação muito suave",
                lighting="luz natural difusa da manhã",
                atmosphere="acolhedora, educativa e realista",
                start=9,
                end=20,
                duration=7,
            ),
            _shot(
                order=3,
                strategy="cinematic_broll",
                purpose="Mostrar objetos e rotina da feira enquanto a narração continua.",
                subject="Medieval market objects, scales, grains, pottery and natural fabrics",
                environment="Corredor central da feira medieval",
                action="Detalhes de mãos pesando grãos e organizando cerâmicas",
                framing="close-ups documentais",
                movement="panorâmica lateral lenta",
                lighting="luz solar filtrada por coberturas de tecido",
                atmosphere="observacional, tátil e historicamente plausível",
                start=20,
                end=30,
                duration=7,
            ),
            _shot(
                order=4,
                strategy="avatar_anchor",
                purpose="Levar o personagem à botica para avançar a explicação.",
                subject="The same approved doctor speaking inside a medieval apothecary",
                environment="Botica de madeira com ervas secas, pilões e frascos de época",
                action="O médico aponta discretamente para a bancada e volta a olhar a câmera",
                framing="plano americano",
                movement="câmera estável com leve aproximação",
                lighting="luz lateral de janela e velas ao fundo",
                atmosphere="investigativa, segura e sem fantasia excessiva",
                start=30,
                end=40,
                duration=7,
            ),
            _shot(
                order=5,
                strategy="cinematic_broll",
                purpose="Apoiar visualmente o contraste entre passado e evidência atual.",
                subject="Period-accurate herbs, mortar, handwritten parchment and apothecary tools",
                environment="Bancada da mesma botica medieval",
                action="A câmera percorre os elementos em profundidade rasa e ritmo calmo",
                framing="macro e planos detalhe",
                movement="deslizamento lento sobre a bancada",
                lighting="contraste suave entre janela e velas",
                atmosphere="científica, histórica e contemplativa",
                start=40,
                end=53,
                duration=9,
            ),
            _shot(
                order=6,
                strategy="avatar_anchor",
                purpose="Encerrar com o personagem e uma orientação médica responsável.",
                subject="The same approved doctor closing the story at the apothecary doorway",
                environment="Porta da botica com a feira medieval desfocada ao fundo",
                action="O médico encerra olhando para a câmera enquanto uma luz discreta sugere o retorno",
                framing="plano médio fechado",
                movement="aproximação final suave",
                lighting="fim de tarde quente com recorte natural",
                atmosphere="confiante, responsável e esperançosa",
                start=53,
                end=76,
                duration=12,
            ),
        ],
    }


def medieval_source() -> dict:
    return {
        "script": {"id": "script-medieval", "status": "aprovado_clinicamente"},
        "editorState": {"humanReviewApproved": True},
        "speech": SPEECH,
        "scriptRevision": 7,
        "finalSpeechHash": SPEECH_HASH,
        "scriptContractVersion": "script-editor-v1",
    }
