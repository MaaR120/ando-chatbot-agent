"""
Chat History Service.
Persists and retrieves conversations and messages from PostgreSQL (conversaciones_ia and mensajes_ia).
"""
import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from app.core.database import get_engine

logger = logging.getLogger(__name__)

DEFAULT_DEMO_USER_ID = "8addc001-3489-4811-b84f-4c7be7bfce02"


class ChatHistoryService:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id or DEFAULT_DEMO_USER_ID
        self.engine = get_engine()

    def get_or_create_conversation(self, conversation_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """
        Devuelve el conversation_id si existe y es válido, o crea una nueva conversación.
        """
        with self.engine.begin() as conn:
            if conversation_id:
                check_query = text(
                    'SELECT id FROM public.conversaciones_ia WHERE id = :id AND "usuarioId" = :user_id'
                )
                row = conn.execute(check_query, {"id": conversation_id, "user_id": self.user_id}).first()
                if row:
                    return str(row[0])

            context_json = json.dumps({"titulo": title or "Nueva conversación"})
            create_query = text("""
                INSERT INTO public.conversaciones_ia ("usuarioId", "activa", "cantidadMensajes", "totalTokensUsados", "contexto")
                VALUES (:user_id, true, 0, 0, CAST(:contexto AS jsonb))
                RETURNING id
            """)
            result = conn.execute(create_query, {
                "user_id": self.user_id,
                "contexto": context_json,
            })
            new_id = result.scalar()
            return str(new_id)

    def list_conversations(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Lista las conversaciones del usuario con su título y fecha más reciente.
        """
        query = text("""
            SELECT 
                c.id,
                c."usuarioId" AS usuario_id,
                c."fechaInicio" AS fecha_inicio,
                c."activa",
                c."cantidadMensajes" AS cantidad_mensajes,
                COALESCE(c.contexto->>'titulo', (
                    SELECT SUBSTRING(m.contenido, 1, 40) 
                    FROM public.mensajes_ia m 
                    WHERE m."conversacionId" = c.id AND m.rol IN ('usuario', 'user') 
                    ORDER BY m."fechaCreacion" ASC LIMIT 1
                ), 'Nueva conversación') AS titulo
            FROM public.conversaciones_ia c
            WHERE c."usuarioId" = :user_id
            ORDER BY c."fechaInicio" DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"user_id": self.user_id, "limit": limit}).mappings().fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "usuario_id": str(r["usuario_id"]),
                    "fecha_inicio": r["fecha_inicio"].isoformat() if r["fecha_inicio"] else "",
                    "activa": bool(r["activa"]),
                    "cantidad_mensajes": int(r["cantidad_mensajes"]),
                    "titulo": r["titulo"],
                }
                for r in rows
            ]

    def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Devuelve todos los mensajes ordenados cronológicamente de una conversación.
        """
        query = text("""
            SELECT 
                m.id,
                m.rol,
                m.contenido,
                m."fechaCreacion" AS fecha_creacion
            FROM public.mensajes_ia m
            JOIN public.conversaciones_ia c ON m."conversacionId" = c.id
            WHERE m."conversacionId" = :conv_id AND c."usuarioId" = :user_id
            ORDER BY m."fechaCreacion" ASC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"conv_id": conversation_id, "user_id": self.user_id}).mappings().fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "rol": r["rol"],
                    "contenido": r["contenido"],
                    "fecha_creacion": r["fecha_creacion"].isoformat() if r["fecha_creacion"] else "",
                }
                for r in rows
            ]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tokens_used: int = 0,
        update_title_if_first: bool = False,
    ) -> None:
        """
        Agrega un mensaje a la conversación y actualiza los contadores.
        """
        with self.engine.begin() as conn:
            insert_msg = text("""
                INSERT INTO public.mensajes_ia ("conversacionId", "rol", "contenido", "tokensUsados")
                VALUES (:conv_id, :rol, :contenido, :tokens)
            """)
            conn.execute(insert_msg, {
                "conv_id": conversation_id,
                "rol": role,
                "contenido": content,
                "tokens": tokens_used,
            })

            update_conv = text("""
                UPDATE public.conversaciones_ia
                SET "cantidadMensajes" = "cantidadMensajes" + 1,
                    "totalTokensUsados" = "totalTokensUsados" + :tokens
                WHERE id = :conv_id
            """)
            conn.execute(update_conv, {"conv_id": conversation_id, "tokens": tokens_used})

            if update_title_if_first:
                # Si el título actual es genérico, actualizarlo con el primer mensaje del usuario
                title = content.strip().replace("\n", " ")[:40]
                if len(content.strip()) > 40:
                    title += "..."
                update_title = text("""
                    UPDATE public.conversaciones_ia
                    SET contexto = jsonb_set(COALESCE(contexto, CAST('{}' AS jsonb)), '{titulo}', to_jsonb(CAST(:title AS text)))
                    WHERE id = :conv_id AND (contexto->>'titulo' IS NULL OR contexto->>'titulo' = 'Nueva conversación')
                """)
                conn.execute(update_title, {"conv_id": conversation_id, "title": title})

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Elimina una conversación y sus mensajes asociados.
        """
        with self.engine.begin() as conn:
            # Primero eliminar mensajes
            conn.execute(
                text('DELETE FROM public.mensajes_ia WHERE "conversacionId" = :conv_id'),
                {"conv_id": conversation_id},
            )
            res = conn.execute(
                text('DELETE FROM public.conversaciones_ia WHERE id = :conv_id AND "usuarioId" = :user_id'),
                {"conv_id": conversation_id, "user_id": self.user_id},
            )
            return res.rowcount > 0

