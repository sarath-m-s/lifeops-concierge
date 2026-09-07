import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AudioSession } from '@livekit/react-native';
import { RemoteAudioTrack, Room, RoomEvent } from 'livekit-client';
import { AgentTurn, ChatMessage } from '../types/agent';
import { api } from '../services/api';

const id = () => Math.random().toString(36).slice(2);

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

/** A live, not-yet-finalised line — replaced in place until the turn it belongs
 * to lands (lk.transcription for the user's own speech) or is superseded by the
 * authoritative lifeops.turn message (the agent's side). */
export interface Caption {
  role: 'user' | 'assistant';
  text: string;
}

interface ChatState {
  messages: ChatMessage[];
  caption: Caption | null;
  connectionState: ConnectionState;
  micActive: boolean;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  sendText: (text: string) => Promise<void>;
  startTalking: () => Promise<void>;
  stopTalking: () => Promise<void>;
  setSpeakerMuted: (muted: boolean) => void;
  reset: () => Promise<void>;
}

const WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: "I can book a table, order food, or restock groceries. Hold the mic and talk, or type below.",
  timestamp: new Date(),
};

/** Never render an empty error. `??` only guards null/undefined, so a blank
 *  message string used to produce a red box with no text in it. */
function describeError(e: unknown): string {
  const raw = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
  const text = raw.trim();
  if (!text) return "That didn't go through. Try again?";
  if (/network request failed|failed to fetch/i.test(text)) {
    return "Can't reach the server. Is the backend running?";
  }
  return text;
}

const Ctx = createContext<ChatState | null>(null);

/** Owns the one LiveKit Room for the whole app — a context, not a plain hook,
 * because Settings needs to mute the same live room Chat is talking through;
 * two independent hook calls would each open their own room. */
export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [caption, setCaption] = useState<Caption | null>(null);
  const [micActive, setMicActive] = useState(false);
  const roomRef = useRef<Room | null>(null);

  const appendMessage = useCallback((partial: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    setMessages((prev) => [...prev, { id: id(), timestamp: new Date(), ...partial }]);
  }, []);

  // One combined {say, components} payload per finished turn, whether it started
  // from voice or typed lk.chat text — see backend/app/voice/worker.py. This is
  // the only thing that finalises an assistant bubble; lk.transcription below is
  // caption-only and never on its own.
  const handleTurn = useCallback(async (raw: string) => {
    let turn: AgentTurn;
    try {
      turn = JSON.parse(raw);
    } catch {
      return;
    }
    setCaption(null);
    if (turn.say || turn.components?.length) {
      appendMessage({ role: 'assistant', text: turn.say, components: turn.components });
    }
  }, [appendMessage]);

  // Built-in transcription topic — free, no backend wiring needed. Interim
  // captions (either side) are shown as a transient line; a FINAL user caption
  // is the only source of "what did I say" for spoken input, so it becomes a
  // permanent bubble here. A final assistant caption is not — that role is
  // lifeops.turn's alone, so an assistant interim line just waits to be cleared
  // by the matching turn message.
  const handleTranscription = useCallback(
    (
      reader: { info: { attributes?: Record<string, string> }; readAll: () => Promise<string> },
      participantInfo: { identity: string },
    ) => {
      reader.readAll().then((text) => {
        const isLocal = participantInfo.identity === roomRef.current?.localParticipant.identity;
        const final = reader.info.attributes?.['lk.transcription_final'] === 'true';
        if (isLocal && final) {
          setCaption(null);
          appendMessage({ role: 'user', text });
          return;
        }
        setCaption({ role: isLocal ? 'user' : 'assistant', text });
      });
    },
    [appendMessage],
  );

  const connect = useCallback(async () => {
    if (roomRef.current) return;
    setConnectionState('connecting');
    try {
      await AudioSession.startAudioSession();
      const { token, url } = await api.getLiveKitToken();
      const room = new Room();
      room.on(RoomEvent.Reconnecting, () => setConnectionState('reconnecting'));
      room.on(RoomEvent.Reconnected, () => setConnectionState('connected'));
      room.on(RoomEvent.Disconnected, () => setConnectionState('disconnected'));
      room.registerTextStreamHandler('lifeops.turn', async (reader) => {
        await handleTurn(await reader.readAll());
      });
      room.registerTextStreamHandler('lk.transcription', handleTranscription);
      await room.connect(url, token);
      roomRef.current = room;
      setConnectionState('connected');
    } catch (e) {
      roomRef.current = null;
      setConnectionState('idle');
      appendMessage({ role: 'assistant', text: describeError(e), failed: true });
    }
  }, [handleTurn, handleTranscription, appendMessage]);

  const disconnect = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    await room?.disconnect();
    await AudioSession.stopAudioSession();
    setConnectionState('idle');
    setCaption(null);
    setMicActive(false);
  }, []);

  // Leave the room if the app unmounts entirely — not on every re-render,
  // since this effect has no reactive dependencies.
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  const sendText = useCallback(async (text: string) => {
    const room = roomRef.current;
    if (!room) return;
    appendMessage({ role: 'user', text });
    try {
      await room.localParticipant.sendText(text, { topic: 'lk.chat' });
    } catch (e) {
      appendMessage({ role: 'assistant', text: describeError(e), failed: true });
    }
  }, [appendMessage]);

  const startTalking = useCallback(async () => {
    if (!roomRef.current) return;
    setMicActive(true);
    await roomRef.current.localParticipant.setMicrophoneEnabled(true);
  }, []);

  const stopTalking = useCallback(async () => {
    if (!roomRef.current) return;
    await roomRef.current.localParticipant.setMicrophoneEnabled(false);
    setMicActive(false);
  }, []);

  /** Client-side preference only — mutes local playback of the agent's voice,
   * does not touch what's published or transcribed. */
  const setSpeakerMuted = useCallback((muted: boolean) => {
    roomRef.current?.remoteParticipants.forEach((participant) => {
      participant.audioTrackPublications.forEach((pub) => {
        if (pub.track instanceof RemoteAudioTrack) pub.track.setVolume(muted ? 0 : 1);
      });
    });
  }, []);

  const reset = useCallback(async () => {
    // Clears the legacy REST agent's conversation store (harmless no-op once
    // that path is retired) and the local transcript. The voice worker's own
    // per-session Conversation cache (backend/app/services/conversation.py) is
    // not cleared by this — there is no room-side reset signal yet, so a long
    // conversation's history keeps accumulating server-side until the worker
    // process restarts. Follow-up work, not done here.
    await api.resetConversation().catch(() => undefined);
    setMessages([WELCOME]);
    setCaption(null);
  }, []);

  const value = useMemo<ChatState>(
    () => ({
      messages, caption, connectionState, micActive,
      connect, disconnect, sendText, startTalking, stopTalking, setSpeakerMuted, reset,
    }),
    [messages, caption, connectionState, micActive, connect, disconnect, sendText, startTalking, stopTalking, setSpeakerMuted, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChat(): ChatState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useChat must be used inside ChatProvider');
  return ctx;
}
