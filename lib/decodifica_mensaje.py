
from ls_message_parsing import (decode_msg, encode_msg,
                                 MessageDecodingError,
                                 MessageEncodingError)


def decodifica_mensaje(mensaje_codificado):
    """
    Decodifica un mensaje codificado utilizando la librería ls_message_parsing.

    Args:
        mensaje_codificado (str): El mensaje codificado a decodificar.

    Returns:
        dict: El mensaje decodificado en formato de diccionario.

    Raises:
        MessageDecodingError: Si ocurre un error durante la decodificación.
    """
    try:
        mensaje_decodificado =b"mensaje_codificado"
        respuesta = decode_msg(mensaje_decodificado).get_decoded_msg_dict()
        return respuesta
    except MessageDecodingError as e:
        raise MessageDecodingError(f"Error al decodificar el mensaje: {e}")

def main():
    mensaje_codificado = "\x40\x57\x08\xAE\x0F\x4F\x00\x00\x12\xD7\x00\x00\x12\xD7\x1E\xE1\xB0\x08\xAE\x03\x02\x00\x00"
    try:
        mensaje_decodificado = decodifica_mensaje(mensaje_codificado)
        print("Mensaje decodificado:", mensaje_decodificado)
    except MessageDecodingError as e:
        print(e)
if __name__ == "__main__":
    main()