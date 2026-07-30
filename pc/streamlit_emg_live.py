"""
Live ParkEMG BLE viewer.

Run:
  streamlit run streamlit_emg_live.py

The BLE acquisition runs in a background thread. Streamlit only reads a snapshot
from a ring buffer and decimates it for display, so plotting load does not block
BLE notifications.
"""
# 11 17 23 27 33 45 57
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import streamlit as st
except ImportError:
    st = None

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = None
    BleakScanner = None

try:
    from emg_defaults import (
        ACTUAL_SAMPLE_RATE_HZ,
        DEFAULT_BAND_PASS_HIGH_HZ,
        DEFAULT_BAND_PASS_LOW_HZ,
        DEFAULT_FILTER_ORDER,
        DEFAULT_NOTCH_HIGH_HZ,
        DEFAULT_NOTCH_LOW_HZ,
        DEFAULT_NOTCH_PASSBAND_RIPPLE_DB,
        DEFAULT_NOTCH_STOPBAND_ATTENUATION_DB,
        DEFAULT_NOTCH_TRANSITION_HZ,
    )
    from emg_filters import (
        apply_emg_filter_chain,
        contiguous_ranges_from_sequences,
    )
except ImportError:
    ACTUAL_SAMPLE_RATE_HZ = 1750.0
    DEFAULT_BAND_PASS_LOW_HZ = 20.0
    DEFAULT_BAND_PASS_HIGH_HZ = 500.0
    DEFAULT_FILTER_ORDER = 8
    DEFAULT_NOTCH_LOW_HZ = 49.0
    DEFAULT_NOTCH_HIGH_HZ = 51.0
    DEFAULT_NOTCH_TRANSITION_HZ = 1.0
    DEFAULT_NOTCH_PASSBAND_RIPPLE_DB = 1.0
    DEFAULT_NOTCH_STOPBAND_ATTENUATION_DB = 40.0
    apply_emg_filter_chain = None
    contiguous_ranges_from_sequences = None


DEFAULT_NAME = "ParkEMG"
DEFAULT_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
DEFAULT_COMMAND_CHAR_UUID = "beb5483e-36e1-4688-b7f5-aeeeee000000"
DEFAULT_EMG_CHAR_UUID = "beb5483e-36e1-4688-b7f5-eeeeeeeeeeee"
ADS1298_FRAME_SIZE = 27
ADS1298_STATUS_SIZE = 3
ADS1298_NUM_CHANNELS = 8
ADS1298_CHANNEL_PAYLOAD_SIZE = ADS1298_NUM_CHANNELS * 3
AVERAGE_CHANNEL = "AVG"
DISPLAY_CHANNEL_OPTIONS = list(range(1, ADS1298_NUM_CHANNELS + 1)) + [AVERAGE_CHANNEL]
EMG_PACKET_MAGIC = b"PE"
EMG_PACKET_VERSION = 1
EMG_PACKET_HEADER_SIZE = 8
EMG_PACKET_CRC_SIZE = 2
EMG_PACKET_SIZE = EMG_PACKET_HEADER_SIZE + ADS1298_FRAME_SIZE + EMG_PACKET_CRC_SIZE
EMG_BATCH_MAGIC = b"PB"
EMG_BATCH_VERSION = 2
EMG_BATCH_SUPPORTED_VERSIONS = {1, 2}
EMG_BATCH_HEADER_SIZE = 9
EMG_BATCH_CRC_SIZE = 2


@dataclass
class EMGSample:
    index: int
    sequence: int
    sample_time_s: float
    notification_elapsed_s: float
    status0: int
    status1: int
    status2: int
    channels: tuple[int, ...]
    raw_hex: str
    frame_ok: bool


def default_output_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir.parent / "Outputs"
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"emg_live_{timestamp}.csv"


def decode_signed_int24(raw: bytes) -> int:
    value = (raw[0] << 16) | (raw[1] << 8) | raw[2]
    if value & 0x800000:
        value -= 0x1000000
    return value


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def parse_emg_packet(data: bytes) -> dict:
    result = {
        "packet_ok": False,
        "checksum_ok": False,
        "packet_error": "",
        "sequence": "",
        "payload": b"",
    }

    if len(data) != EMG_PACKET_SIZE:
        result["packet_error"] = f"unexpected packet size {len(data)}"
        return result
    if data[0:2] != EMG_PACKET_MAGIC:
        result["packet_error"] = "bad packet magic"
        return result
    if data[2] != EMG_PACKET_VERSION:
        result["packet_error"] = f"unsupported packet version {data[2]}"
        return result

    sequence = int.from_bytes(data[3:7], byteorder="little", signed=False)
    payload_len = data[7]
    result["sequence"] = sequence

    if payload_len != ADS1298_FRAME_SIZE:
        result["packet_error"] = f"unexpected payload size {payload_len}"
        return result

    crc_offset = EMG_PACKET_HEADER_SIZE + payload_len
    received_crc = int.from_bytes(data[crc_offset : crc_offset + 2], byteorder="little", signed=False)
    computed_crc = crc16_ccitt(data[:crc_offset])
    if received_crc != computed_crc:
        result["packet_error"] = f"crc mismatch rx=0x{received_crc:04X} calc=0x{computed_crc:04X}"
        return result

    result["packet_ok"] = True
    result["checksum_ok"] = True
    result["payload"] = data[EMG_PACKET_HEADER_SIZE:crc_offset]
    return result


def build_emg_packet(sequence: int, payload: bytes) -> bytes:
    packet = bytearray(EMG_PACKET_SIZE)
    packet[0:2] = EMG_PACKET_MAGIC
    packet[2] = EMG_PACKET_VERSION
    packet[3:7] = sequence.to_bytes(4, byteorder="little", signed=False)
    packet[7] = len(payload)
    packet[EMG_PACKET_HEADER_SIZE : EMG_PACKET_HEADER_SIZE + len(payload)] = payload
    crc_offset = EMG_PACKET_HEADER_SIZE + len(payload)
    crc = crc16_ccitt(packet[:crc_offset])
    packet[crc_offset : crc_offset + EMG_PACKET_CRC_SIZE] = crc.to_bytes(
        EMG_PACKET_CRC_SIZE, byteorder="little", signed=False
    )
    return bytes(packet)


def iter_emg_packets(data: bytes):
    # El firmware puede enviar un lote PB con varias muestras y un CRC comun.
    # La version 2 omite los 3 bytes de status por muestra para meter mas muestras
    # por notify; aqui se reconstruyen a cero y se reutiliza el parser PE normal.
    if len(data) >= EMG_BATCH_HEADER_SIZE + EMG_BATCH_CRC_SIZE and data[0:2] == EMG_BATCH_MAGIC:
        if data[2] not in EMG_BATCH_SUPPORTED_VERSIONS:
            yield data
            return

        sample_count = data[3]
        first_sequence = int.from_bytes(data[4:8], byteorder="little", signed=False)
        frame_size = data[8]
        payload_len = sample_count * frame_size
        expected_len = EMG_BATCH_HEADER_SIZE + payload_len + EMG_BATCH_CRC_SIZE
        if (
            sample_count == 0
            or frame_size not in (ADS1298_FRAME_SIZE, ADS1298_CHANNEL_PAYLOAD_SIZE)
            or len(data) != expected_len
        ):
            yield data
            return

        received_crc = int.from_bytes(data[-EMG_BATCH_CRC_SIZE:], byteorder="little", signed=False)
        computed_crc = crc16_ccitt(data[:-EMG_BATCH_CRC_SIZE])
        if received_crc != computed_crc:
            yield data
            return

        payload = data[EMG_BATCH_HEADER_SIZE : EMG_BATCH_HEADER_SIZE + payload_len]
        for sample_index in range(sample_count):
            sequence = (first_sequence + sample_index) & 0xFFFFFFFF
            offset = sample_index * frame_size
            sample_payload = payload[offset : offset + frame_size]
            if frame_size == ADS1298_CHANNEL_PAYLOAD_SIZE:
                sample_payload = bytes(ADS1298_STATUS_SIZE) + sample_payload
            yield build_emg_packet(sequence, sample_payload)
        return

    if len(data) == EMG_PACKET_SIZE:
        yield data
        return

    if len(data) > EMG_PACKET_SIZE and len(data) % EMG_PACKET_SIZE == 0:
        chunks = [data[offset : offset + EMG_PACKET_SIZE] for offset in range(0, len(data), EMG_PACKET_SIZE)]
        if all(chunk[0:2] == EMG_PACKET_MAGIC for chunk in chunks):
            yield from chunks
            return

    yield data


def decode_ads1298_frame(
    packet_index: int,
    sequence: int,
    sample_time_s: float,
    notification_elapsed_s: float,
    data: bytes,
) -> EMGSample:
    status = [0, 0, 0]
    if len(data) >= 3:
        status = [data[0], data[1], data[2]]

    channels = []
    if len(data) >= ADS1298_FRAME_SIZE:
        for channel in range(ADS1298_NUM_CHANNELS):
            offset = 3 + channel * 3
            channels.append(decode_signed_int24(data[offset : offset + 3]))

    while len(channels) < ADS1298_NUM_CHANNELS:
        channels.append(0)

    return EMGSample(
        index=packet_index,
        sequence=sequence,
        sample_time_s=sample_time_s,
        notification_elapsed_s=notification_elapsed_s,
        status0=status[0],
        status1=status[1],
        status2=status[2],
        channels=tuple(channels),
        raw_hex=data.hex(),
        frame_ok=len(data) == ADS1298_FRAME_SIZE,
    )


class EMGRecorder:
    def __init__(
        self,
        *,
        address: str,
        name: str,
        service_uuid: str,
        command_char_uuid: str,
        emg_char_uuid: str,
        output_path: Path,
        buffer_seconds: float,
        expected_fs_hz: float,
        start_command: str,
        stop_command: str,
    ) -> None:
        maxlen = max(100, int(buffer_seconds * expected_fs_hz * 1.5))
        self.address = address
        self.name = name
        self.service_uuid = service_uuid.lower()
        self.command_char_uuid = command_char_uuid.lower()
        self.emg_char_uuid = emg_char_uuid.lower()
        self.output_path = output_path
        self.expected_fs_hz = max(float(expected_fs_hz), 1.0)
        self.start_command = start_command.strip()
        self.stop_command = stop_command.strip()
        # Streamlit reruns the UI script often; BLE commands are queued here and
        # drained by the persistent BLE thread so button clicks do not block.
        self.command_queue: Queue[str] = Queue()

        self.samples: deque[EMGSample] = deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.started_at = time.monotonic()
        self.last_packet_at: Optional[float] = None
        self.status = "Idle"
        self.error = ""
        self.packet_count = 0
        self.valid_packet_count = 0
        self.byte_count = 0
        self.malformed_count = 0
        self.checksum_error_count = 0
        self.dropped_packet_count = 0
        self.sequence_gap_count = 0
        self.duplicate_sequence_count = 0
        self.last_sequence: Optional[int] = None
        self.first_sequence: Optional[int] = None
        self.connected = False
        self.command_notifications = 0
        self.last_command = ""
        self.last_command_error = ""
        self.subscribed_characteristics: tuple[str, ...] = ()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._thread_main, name="parkemg-ble", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        # This only stops the Python BLE session. It deliberately does not send
        # stop_EMG; EMG acquisition is stopped only by the Stop EMG button.
        self.stop_event.set()

    def is_alive(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def snapshot(self) -> tuple[list[EMGSample], dict]:
        with self.lock:
            samples = list(self.samples)
            elapsed = max(time.monotonic() - self.started_at, 1e-6)
            recent_elapsed = None
            if len(samples) >= 2:
                recent_elapsed = max(samples[-1].sample_time_s - samples[0].sample_time_s, 1e-6)

            stats = {
                "status": self.status,
                "error": self.error,
                "connected": self.connected,
                "packets": self.packet_count,
                "valid_packets": self.valid_packet_count,
                "bytes": self.byte_count,
                "malformed": self.malformed_count,
                "checksum_errors": self.checksum_error_count,
                "dropped_packets": self.dropped_packet_count,
                "sequence_gaps": self.sequence_gap_count,
                "duplicate_sequences": self.duplicate_sequence_count,
                "avg_rate_hz": self.packet_count / elapsed,
                "buffer_rate_hz": (len(samples) - 1) / recent_elapsed if recent_elapsed else 0.0,
                "buffer_samples": len(samples),
                "output_path": str(self.output_path),
                "command_notifications": self.command_notifications,
                "last_command": self.last_command,
                "last_command_error": self.last_command_error,
                "subscribed_characteristics": self.subscribed_characteristics,
                "last_packet_age_s": (
                    time.monotonic() - self.last_packet_at if self.last_packet_at is not None else None
                ),
            }
        return samples, stats

    def queue_command(self, command: str) -> None:
        command = command.strip()
        if not command:
            return
        self.command_queue.put(command)
        with self.lock:
            self.last_command = command
            self.last_command_error = ""

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_ble())
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.status = "Error"
                self.connected = False

    async def _find_device(self):
        if self.address:
            return self.address

        self._set_status(f"Scanning for {self.name}...")
        devices = await BleakScanner.discover(timeout=10.0)
        for device in devices:
            if device.name and self.name.lower() in device.name.lower():
                return device.address

        raise RuntimeError(f"Device not found by name: {self.name}")

    async def _write_command(self, client, char_uuid: str, command: str) -> None:
        if not command:
            return
        await client.write_gatt_char(char_uuid, (command + "\n").encode("utf-8"), response=False)
        with self.lock:
            self.last_command = command
            self.last_command_error = ""

    async def _drain_command_queue(self, client, char_uuid: str) -> None:
        while True:
            try:
                command = self.command_queue.get_nowait()
            except Empty:
                return

            try:
                await self._write_command(client, char_uuid, command)
            except Exception as exc:
                with self.lock:
                    self.last_command = command
                    self.last_command_error = str(exc)

    async def _run_ble(self) -> None:
        if BleakClient is None or BleakScanner is None:
            raise RuntimeError("Missing bleak. Install it with: py -3.13 -m pip install bleak")

        address = await self._find_device()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.started_at = time.monotonic()

        with self.output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self._csv_headers())
            writer.writeheader()

            self._set_status(f"Connecting to {address}...")
            async with BleakClient(address, timeout=20.0) as client:
                self._set_connected(True)
                service, notify_chars, command_char = self._resolve_gatt(client)

                self._set_status("Subscribing to BLE notifications...")

                def make_notification_handler(source_uuid: str):
                    def on_notification(sender, data: bytearray) -> None:
                        raw = bytes(data)
                        if source_uuid.lower() == self.command_char_uuid:
                            with self.lock:
                                self.command_notifications += 1

                        for packet_raw in iter_emg_packets(raw):
                            packet_index = self.packet_count + 1
                            parsed = parse_emg_packet(packet_raw)
                            sample = None
                            if parsed["packet_ok"]:
                                notification_elapsed_s = time.monotonic() - self.started_at
                                sample_time_s = self._sample_time_from_sequence(parsed["sequence"])
                                sample = decode_ads1298_frame(
                                    packet_index,
                                    parsed["sequence"],
                                    sample_time_s,
                                    notification_elapsed_s,
                                    parsed["payload"],
                                )

                            sequence_gap = self._record_packet(sample, len(packet_raw), parsed)
                            writer.writerow(self._csv_row(packet_index, sample, source_uuid, packet_raw, parsed, sequence_gap))
                            if packet_index % 100 == 0:
                                csv_file.flush()

                    return on_notification

                subscribed = []
                for characteristic in notify_chars:
                    source_uuid = str(characteristic.uuid)
                    await client.start_notify(characteristic.uuid, make_notification_handler(source_uuid))
                    subscribed.append(str(characteristic.uuid))

                with self.lock:
                    self.subscribed_characteristics = tuple(subscribed)

                try:
                    self._set_status("Connected")
                    while not self.stop_event.is_set() and client.is_connected:
                        # Keep the BLE connection alive and send pending UI commands.
                        # EMG data arrives asynchronously through notification handlers.
                        await self._drain_command_queue(client, command_char.uuid)
                        await asyncio.sleep(0.05)

                finally:
                    # Do not auto-send stop_EMG on cleanup. Sampling should keep
                    # running until the user presses the Stop EMG button.
                    try:
                        for characteristic in notify_chars:
                            try:
                                await client.stop_notify(characteristic.uuid)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    csv_file.flush()

        self._set_connected(False)
        self._set_status("Stopped")

    def _resolve_gatt(self, client):
        service = None
        for candidate in client.services:
            if str(candidate.uuid).lower() == self.service_uuid:
                service = candidate
                break
        if service is None:
            raise RuntimeError(f"Service not found: {self.service_uuid}")

        command_char = None
        emg_char = None
        for characteristic in service.characteristics:
            uuid = str(characteristic.uuid).lower()
            if uuid == self.emg_char_uuid:
                emg_char = characteristic
            if uuid == self.command_char_uuid:
                command_char = characteristic

        if emg_char is None:
            raise RuntimeError(f"EMG characteristic not found: {self.emg_char_uuid}")
        if "notify" not in emg_char.properties:
            raise RuntimeError(f"EMG characteristic is not notifiable: {emg_char.properties}")
        if command_char is None:
            raise RuntimeError(f"Command characteristic not found: {self.command_char_uuid}")
        if "write" not in command_char.properties and "write-without-response" not in command_char.properties:
            raise RuntimeError(f"Command characteristic is not writable: {command_char.properties}")
        if "notify" not in command_char.properties:
            raise RuntimeError(f"Command characteristic is not notifiable: {command_char.properties}")

        notify_chars = []
        for characteristic in (command_char, emg_char):
            if all(str(existing.uuid).lower() != str(characteristic.uuid).lower() for existing in notify_chars):
                notify_chars.append(characteristic)

        return service, notify_chars, command_char

    def _record_packet(self, sample: Optional[EMGSample], byte_count: int, parsed: dict):
        sequence_gap = ""
        with self.lock:
            self.packet_count += 1
            self.byte_count += byte_count
            self.last_packet_at = time.monotonic()

            if parsed["packet_ok"] and sample is not None:
                if self.status == "Connected":
                    self.status = "Recording"
                self.valid_packet_count += 1
                if self.last_sequence is not None:
                    expected = (self.last_sequence + 1) & 0xFFFFFFFF
                    if sample.sequence == self.last_sequence:
                        self.duplicate_sequence_count += 1
                        self.dropped_packet_count += 1
                        return "duplicate"
                    if sample.sequence != expected:
                        sequence_gap = (sample.sequence - expected) & 0xFFFFFFFF
                        if sequence_gap < 0x80000000:
                            self.sequence_gap_count += sequence_gap
                        else:
                            sequence_gap = "out_of_order"
                self.last_sequence = sample.sequence

                if sample.frame_ok:
                    self.samples.append(sample)
                else:
                    self.malformed_count += 1
                    self.dropped_packet_count += 1
            else:
                self.dropped_packet_count += 1
                if "crc mismatch" in parsed["packet_error"]:
                    self.checksum_error_count += 1
                else:
                    self.malformed_count += 1

        return sequence_gap

    def _sample_time_from_sequence(self, sequence: int) -> float:
        if self.first_sequence is None:
            self.first_sequence = sequence
        return ((sequence - self.first_sequence) & 0xFFFFFFFF) / self.expected_fs_hz

    def _set_status(self, status: str) -> None:
        with self.lock:
            self.status = status

    def _set_connected(self, connected: bool) -> None:
        with self.lock:
            self.connected = connected

    @staticmethod
    def _csv_headers() -> list[str]:
        return [
            "timestamp_iso",
            "elapsed_s",
            "sample_time_s",
            "notification_elapsed_s",
            "packet_index",
            "sender",
            "len_bytes",
            "packet_ok",
            "checksum_ok",
            "sequence",
            "sequence_gap",
            "packet_error",
            "frame_ok",
            "status0",
            "status1",
            "status2",
            "ch1",
            "ch2",
            "ch3",
            "ch4",
            "ch5",
            "ch6",
            "ch7",
            "ch8",
            "raw_hex",
        ]

    @staticmethod
    def _csv_row(packet_index: int, sample: Optional[EMGSample], sender, raw: bytes, parsed: dict, sequence_gap) -> dict:
        row = {
            "timestamp_iso": dt.datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_s": f"{sample.sample_time_s:.6f}" if sample else "",
            "sample_time_s": f"{sample.sample_time_s:.6f}" if sample else "",
            "notification_elapsed_s": f"{sample.notification_elapsed_s:.6f}" if sample else "",
            "packet_index": packet_index,
            "sender": sender,
            "len_bytes": len(raw),
            "packet_ok": parsed["packet_ok"],
            "checksum_ok": parsed["checksum_ok"],
            "sequence": parsed["sequence"],
            "sequence_gap": sequence_gap,
            "packet_error": parsed["packet_error"],
            "frame_ok": sample.frame_ok if sample else False,
            "status0": f"0x{sample.status0:02X}" if sample else "",
            "status1": f"0x{sample.status1:02X}" if sample else "",
            "status2": f"0x{sample.status2:02X}" if sample else "",
            "raw_hex": raw.hex(),
        }
        for idx in range(1, ADS1298_NUM_CHANNELS + 1):
            row[f"ch{idx}"] = sample.channels[idx - 1] if sample else ""
        return row


def decimate_samples(samples: list[EMGSample], max_points: int) -> tuple[list[EMGSample], int]:
    if len(samples) <= max_points:
        return samples, 1
    stride = max(1, math.ceil(len(samples) / max_points))
    return samples[::stride], stride


def display_channel_label(channel) -> str:
    if channel == AVERAGE_CHANNEL:
        return AVERAGE_CHANNEL
    return f"CH{channel}"


def display_channel_offset_index(channel) -> int:
    if channel == AVERAGE_CHANNEL:
        return ADS1298_NUM_CHANNELS
    return int(channel) - 1


def sample_channel_value(sample: EMGSample, channel) -> float:
    if channel == AVERAGE_CHANNEL:
        return sum(sample.channels) / ADS1298_NUM_CHANNELS
    return float(sample.channels[int(channel) - 1])


def band_pass_channel_values(
    samples: list[EMGSample],
    channel,
    low_cutoff_hz: float,
    high_cutoff_hz: float,
    fs_hz: float,
    order: int,
) -> list[float]:
    values = [sample_channel_value(sample, channel) for sample in samples]
    ranges = contiguous_ranges_from_sequences([sample.sequence for sample in samples])
    return apply_emg_filter_chain(
        values,
        ranges,
        band_pass_low_hz=low_cutoff_hz,
        band_pass_high_hz=high_cutoff_hz,
        band_pass_order=order,
        notch_low_hz=DEFAULT_NOTCH_LOW_HZ,
        notch_high_hz=DEFAULT_NOTCH_HIGH_HZ,
        notch_transition_hz=DEFAULT_NOTCH_TRANSITION_HZ,
        notch_passband_ripple_db=DEFAULT_NOTCH_PASSBAND_RIPPLE_DB,
        notch_stopband_attenuation_db=DEFAULT_NOTCH_STOPBAND_ATTENUATION_DB,
        fs_hz=fs_hz,
    )


def samples_to_dataframe(
    samples: list[EMGSample],
    *,
    selected_channels: list,
    offset: float,
    remove_dc: bool,
    band_pass_low_hz: float,
    band_pass_high_hz: float,
    filter_order: int,
    fs_hz: float,
    max_points: int,
) -> tuple["pd.DataFrame", int, int]:
    if not samples:
        return pd.DataFrame(), 1, 0

    stride = max(1, math.ceil(len(samples) / max_points)) if max_points > 0 else 1
    plot_indices = list(range(0, len(samples), stride))
    filtered_values = {
        channel: band_pass_channel_values(
            samples,
            channel,
            band_pass_low_hz,
            band_pass_high_hz,
            fs_hz,
            filter_order,
        )
        for channel in selected_channels
    }

    means = {channel: 0.0 for channel in selected_channels}
    if remove_dc:
        for channel in selected_channels:
            means[channel] = sum(filtered_values[channel][idx] for idx in plot_indices) / len(plot_indices)

    rows = []
    previous_sample: Optional[EMGSample] = None
    for sample_idx in plot_indices:
        sample = samples[sample_idx]
        if previous_sample is not None:
            sequence_delta = (sample.sequence - previous_sample.sequence) & 0xFFFFFFFF
            if 0 < sequence_delta < 0x80000000 and sequence_delta > stride:
                # Insert NaN only for real acquisition gaps. This breaks the line
                # visually without treating normal plot decimation as missing data.
                gap_t = (previous_sample.sample_time_s + sample.sample_time_s) / 2.0
                gap_row = {"t_s": gap_t}
                for channel in selected_channels:
                    gap_row[display_channel_label(channel)] = math.nan
                rows.append(gap_row)

        row = {"t_s": sample.sample_time_s}
        for channel in selected_channels:
            value = filtered_values[channel][sample_idx] - means[channel]
            row[display_channel_label(channel)] = value + offset * display_channel_offset_index(channel)
        rows.append(row)
        previous_sample = sample

    return pd.DataFrame(rows).set_index("t_s"), stride, len(plot_indices)


def ensure_dependencies() -> None:
    missing = []
    if st is None:
        missing.append("streamlit")
    if pd is None:
        missing.append("pandas")
    if BleakClient is None:
        missing.append("bleak")
    if apply_emg_filter_chain is None or contiguous_ranges_from_sequences is None:
        missing.append("scipy")

    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Install them with: py -3.13 -m pip install streamlit pandas bleak scipy")
        raise SystemExit(2)


def sidebar_config() -> dict:
    if "live_default_output_path" not in st.session_state:
        st.session_state.live_default_output_path = str(default_output_path())

    st.sidebar.header("BLE")
    address = st.sidebar.text_input("Address", value="", help="Leave empty to scan by device name.")
    name = st.sidebar.text_input("Name filter", value=DEFAULT_NAME)

    st.sidebar.header("Acquisition")
    expected_fs_hz = st.sidebar.number_input(
        "Actual sample rate (Hz)",
        min_value=1,
        max_value=10000,
        value=int(ACTUAL_SAMPLE_RATE_HZ),
    )
    buffer_seconds = st.sidebar.number_input("RAM buffer (s)", min_value=2, max_value=300, value=10)
    start_command = st.sidebar.text_input("Start command", value="start_EMG")
    stop_command = st.sidebar.text_input("Stop command", value="stop_EMG")

    st.sidebar.header("Display")
    window_seconds = st.sidebar.slider("Window (s)", min_value=0.1, max_value=30.0, value=0.5, step=0.1)
    max_plot_points = st.sidebar.slider("Max plot points", min_value=200, max_value=5000, value=300, step=100)
    refresh_interval = st.sidebar.slider("Refresh interval (s)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
    offset = st.sidebar.number_input("Channel offset", min_value=0, max_value=10_000_000, value=500_000, step=50_000)
    nyquist_hz = float(expected_fs_hz) / 2.0
    band_pass_low_hz = st.sidebar.number_input(
        "Band-pass low cutoff (Hz)",
        min_value=0.1,
        max_value=max(0.1, nyquist_hz - 0.2),
        value=min(DEFAULT_BAND_PASS_LOW_HZ, max(0.1, nyquist_hz - 0.2)),
        step=5.0,
    )
    band_pass_high_hz = st.sidebar.number_input(
        "Band-pass high cutoff (Hz)",
        min_value=min(float(band_pass_low_hz) + 0.1, nyquist_hz - 0.1),
        max_value=max(float(band_pass_low_hz) + 0.1, nyquist_hz - 0.1),
        value=min(DEFAULT_BAND_PASS_HIGH_HZ, nyquist_hz - 0.1),
        step=5.0,
    )
    filter_order = st.sidebar.number_input(
        "Band-pass design order",
        min_value=1,
        max_value=12,
        value=DEFAULT_FILTER_ORDER,
        step=1,
        help="The display applies the filter forwards and backwards for zero phase.",
    )
    remove_dc = st.sidebar.checkbox("Remove DC in displayed window", value=True)
    selected_channels = st.sidebar.multiselect(
        "Channels",
        options=DISPLAY_CHANNEL_OPTIONS,
        default=DISPLAY_CHANNEL_OPTIONS,
        format_func=display_channel_label,
    )

    st.sidebar.header("Output")
    output_path = st.sidebar.text_input("CSV path", value=st.session_state.live_default_output_path)

    return {
        "address": address.strip(),
        "name": name.strip(),
        "expected_fs_hz": float(expected_fs_hz),
        "buffer_seconds": float(buffer_seconds),
        "start_command": start_command,
        "stop_command": stop_command,
        "window_seconds": float(window_seconds),
        "max_plot_points": int(max_plot_points),
        "refresh_interval": float(refresh_interval),
        "offset": float(offset),
        "band_pass_low_hz": float(band_pass_low_hz),
        "band_pass_high_hz": float(band_pass_high_hz),
        "filter_order": int(filter_order),
        "remove_dc": bool(remove_dc),
        "selected_channels": selected_channels,
        "output_path": Path(output_path).expanduser(),
    }


def create_recorder(config: dict) -> EMGRecorder:
    return EMGRecorder(
        address=config["address"],
        name=config["name"],
        service_uuid=DEFAULT_SERVICE_UUID,
        command_char_uuid=DEFAULT_COMMAND_CHAR_UUID,
        emg_char_uuid=DEFAULT_EMG_CHAR_UUID,
        output_path=config["output_path"],
        buffer_seconds=config["buffer_seconds"],
        expected_fs_hz=config["expected_fs_hz"],
        start_command=config["start_command"],
        stop_command=config["stop_command"],
    )


def render_app() -> None:
    st.set_page_config(page_title="ParkEMG Live", layout="wide")
    st.title("ParkEMG Live EMG")

    config = sidebar_config()

    if "recorder" not in st.session_state:
        st.session_state.recorder = None

    control_cols = st.columns([1, 1, 1, 1, 1, 1])
    with control_cols[0]:
        connect_clicked = st.button("Connect", type="primary", use_container_width=True)
    with control_cols[1]:
        disconnect_clicked = st.button("Disconnect", use_container_width=True)
    with control_cols[2]:
        start_emg_clicked = st.button("Start EMG", use_container_width=True)
    with control_cols[3]:
        stop_emg_clicked = st.button("Stop EMG", use_container_width=True)
    with control_cols[4]:
        led_on_clicked = st.button("LED ON", use_container_width=True)
    with control_cols[5]:
        led_off_clicked = st.button("LED OFF", use_container_width=True)

    recorder: Optional[EMGRecorder] = st.session_state.recorder

    if connect_clicked:
        if recorder and recorder.is_alive():
            st.warning("Recorder is already running.")
        else:
            recorder = create_recorder(config)
            st.session_state.recorder = recorder
            recorder.start()

    def queue_recorder_command(command: str) -> None:
        if recorder and recorder.is_alive():
            recorder.queue_command(command)
        else:
            st.warning("Connect before sending commands.")

    if start_emg_clicked:
        # From this point the firmware keeps sampling until stop_EMG is sent.
        queue_recorder_command(config["start_command"])

    if stop_emg_clicked:
        # This is the only UI path that sends stop_EMG.
        queue_recorder_command(config["stop_command"])

    if led_on_clicked:
        queue_recorder_command("LED_ON")

    if led_off_clicked:
        queue_recorder_command("LED_OFF")

    if disconnect_clicked and recorder:
        recorder.stop()

    if recorder:
        samples, stats = recorder.snapshot()
    else:
        samples, stats = [], {
            "status": "Idle",
            "error": "",
            "connected": False,
            "packets": 0,
            "valid_packets": 0,
            "bytes": 0,
            "malformed": 0,
            "checksum_errors": 0,
            "dropped_packets": 0,
            "sequence_gaps": 0,
            "duplicate_sequences": 0,
            "avg_rate_hz": 0.0,
            "buffer_rate_hz": 0.0,
            "buffer_samples": 0,
            "output_path": str(config["output_path"]),
            "command_notifications": 0,
            "last_command": "",
            "last_command_error": "",
            "subscribed_characteristics": (),
            "last_packet_age_s": None,
        }

    metric_cols = st.columns(9)
    metric_cols[0].metric("Status", stats["status"])
    metric_cols[1].metric("Connected", "yes" if stats["connected"] else "no")
    metric_cols[2].metric("Valid", stats["valid_packets"])
    metric_cols[3].metric("Dropped", stats["dropped_packets"])
    metric_cols[4].metric("Avg rate", f"{stats['avg_rate_hz']:.1f} Hz")
    metric_cols[5].metric("Buffer rate", f"{stats['buffer_rate_hz']:.1f} Hz")
    metric_cols[6].metric("CRC errors", stats["checksum_errors"])
    metric_cols[7].metric("Seq gaps", stats["sequence_gaps"])
    metric_cols[8].metric("Duplicates", stats["duplicate_sequences"])

    st.caption(f"CSV: {stats['output_path']}")
    if stats["subscribed_characteristics"]:
        st.caption("Subscribed: " + ", ".join(stats["subscribed_characteristics"]))
    if stats["last_command"]:
        st.caption(f"Last command: {stats['last_command']}")
    if stats["last_command_error"]:
        st.error(f"Command error: {stats['last_command_error']}")
    if stats["error"]:
        st.error(stats["error"])

    if samples:
        latest_t = samples[-1].sample_time_s
        window_start = max(0.0, latest_t - config["window_seconds"])
        window_samples = [sample for sample in samples if sample.sample_time_s >= window_start]

        if config["selected_channels"]:
            df, plot_stride, plotted_count = samples_to_dataframe(
                window_samples,
                selected_channels=config["selected_channels"],
                offset=config["offset"],
                remove_dc=config["remove_dc"],
                band_pass_low_hz=config["band_pass_low_hz"],
                band_pass_high_hz=config["band_pass_high_hz"],
                filter_order=config["filter_order"],
                fs_hz=config["expected_fs_hz"],
                max_points=config["max_plot_points"],
            )
            if df.empty or df.dropna(how="all").empty:
                st.info("Waiting for plottable EMG samples.")
            else:
                st.line_chart(df, height=520)
                st.caption(
                    f"Displaying {plotted_count} of {len(window_samples)} samples "
                    f"in the last {config['window_seconds']:.1f} s. "
                    f"Display band-pass: Butterworth {config['band_pass_low_hz']:.1f}-"
                    f"{config['band_pass_high_hz']:.1f} Hz, "
                    f"design order {config['filter_order']}; notch "
                    f"{DEFAULT_NOTCH_LOW_HZ:.1f}-{DEFAULT_NOTCH_HIGH_HZ:.1f} Hz, zero-phase. "
                    f"Actual sample rate: {config['expected_fs_hz']:.0f} Hz."
                )
        else:
            st.info("Select at least one channel to plot.")
    else:
        st.info("Connect and send Start EMG to begin sampling.")

    if recorder and recorder.is_alive():
        time.sleep(config["refresh_interval"])
        st.rerun()


def main() -> None:
    ensure_dependencies()
    render_app()


if __name__ == "__main__":
    main()
