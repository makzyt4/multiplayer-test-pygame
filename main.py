import socket
import threading
import pickle
import enum
import random
import math
import pygame


BUFFER_SIZE = 4096


class MessageType(enum.Enum):
    GAME_INFO_REQUEST = 0
    GAME_INFO_SEND = 1
    PLAYER_INFO_BROADCAST = 2
    PLAYER_INFO = 3
    NEW_PLAYER_INFO = 4


class Message:
    def __init__(self, type, data=None):
        self.type = type
        self.data = data


class PlayerState(enum.Enum):
    CURRENT = 0
    ONLINE = 1
    OFFLINE = 2


class PlayerConnection:
    def __init__(self, sock, addr, player):
        self.sock = sock
        self.address = addr
        self.player = player
        self.__active = True

    def disconnect(self):
        self.sock.close()
        self.player.state = PlayerState.OFFLINE
        self.__active = False

    def is_active(self):
        return self.__active


class Player:
    def __init__(self, id):
        self.id = id
        self.position = pygame.math.Vector2(0, 0)
        self.velocity = pygame.math.Vector2(0, 0)
        self.angle = 0
        self.speed = 2
        self.state = PlayerState.ONLINE
        self.rect = pygame.Rect(self.position[0], self.position[1], 32, 32)

        self.control_left = False
        self.control_right = False
        self.control_up = False
        self.control_down = False

    def update(self):
        self.position += self.velocity
        self.rect.center = self.position
        self.velocity *= 0.9

        if self.control_left:
            self.velocity[0] = -self.speed
        if self.control_right:
            self.velocity[0] = self.speed
        if self.control_up:
            self.velocity[1] = -self.speed
        if self.control_down:
            self.velocity[1] = self.speed


    def draw(self, surface, pivot):
        if self.state == PlayerState.CURRENT:
            color = (255, 0, 0)
        elif self.state == PlayerState.ONLINE:
            color = (0, 0, 255)
        elif self.state == PlayerState.OFFLINE:
            color = (96, 96, 96)
        image = pygame.Surface((32, 32), pygame.SRCALPHA, 32)
        image.fill(color=color)

        #screen_center = pygame.math.Vector2(surface.get_size()) / 2
        #vector = self.position - pivot
        #relative_position = screen_center + vector

        image = pygame.transform.rotate(image, self.angle)
        surface.blit(image, (self.position[0] - image.get_size()[0] / 2,
                             self.position[1] - image.get_size()[1] / 2))

    def dump_info(self):
        info = {
            'id': self.id,
            'position': self.position,
            'velocity': self.velocity,
            'angle': self.angle,
            'state': self.state
        }
        return info

    def load_info(self, info):
        self.id = info['id']
        self.position = info['position']
        self.velocity = info['velocity']
        self.angle = info['angle']
        self.state = info['state']

    def turn_to(self, point):
        rel_x, rel_y = point - self.position
        self.angle = -math.degrees(math.atan2(rel_y, rel_x))

    def control(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == ord('a'):
                self.control_left = True
            elif event.key == ord('d'):
                self.control_right = True
            elif event.key == ord('w'):
                self.control_up = True
            elif event.key == ord('s'):
                self.control_down = True
        elif event.type == pygame.KEYUP:
            if event.key == ord('a'):
                self.control_left = False
            elif event.key == ord('d'):
                self.control_right = False
            elif event.key == ord('w'):
                self.control_up = False
            elif event.key == ord('s'):
                self.control_down = False


class Game:
    def __init__(self):
        self.players = []

    def update(self):
        for player in self.players:
            player.update()

    def draw(self, surface, center):
        surface.fill((30, 30, 30))

        for player in self.players:
            player.draw(surface, center)

    def dump_info(self):
        info = {
            'players': [p.dump_info() for p in self.players]
        }
        return info

    def load_info(self, info):
        for pi in info['players']:
            player_exists = False
            for p in self.players:
                if p.id == pi['id']:
                    player_exists = True
                    p.load_info(pi)
                    break
            if not player_exists:
                player = Player(len(self.players))
                player.load_info(pi)
                self.players.append(player)


class GameServer:
    def __init__(self, server_address):
        self.game = Game()
        self.connections = []
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(server_address)
        self.server_socket.listen(1)

        threading.Thread(target=self.accept_clients).start()

    def accept_clients(self):
        while True:
            sock, address = self.server_socket.accept()
            print("Client {} connected.".format(address))
            player = Player(len(self.connections))
            self.connections.append(PlayerConnection(sock, address, player))
            self.game.players.append(player)

            player.position = pygame.math.Vector2(random.randint(0, 400), random.randint(0, 300))

            player_info = player.dump_info()
            message = Message(MessageType.NEW_PLAYER_INFO, player_info)
            data = pickle.dumps(message)

            sock.sendall(data)

    def handle_message(self, player_conn, message):
        if message.type == MessageType.GAME_INFO_REQUEST:
            game_info = self.game.dump_info()
            message = Message(MessageType.GAME_INFO_SEND, game_info)
            data = pickle.dumps(message)
            player_conn.sock.sendall(data)
        elif message.type == MessageType.PLAYER_INFO:
            player_info = message.data

            for player in self.game.players:
                if player.state == PlayerState.CURRENT:
                    player.state = PlayerState.ONLINE
                if player.id == player_info['id']:
                    player.load_info(player_info)

            game_info = self.game.dump_info()
            message = Message(MessageType.GAME_INFO_SEND, game_info)
            data = pickle.dumps(message)
            player_conn.sock.sendall(data)

    def loop(self):
        while True:
            for conn in [c for c in self.connections if c.is_active()]:
                try:
                    data = conn.sock.recv(BUFFER_SIZE)
                    message = pickle.loads(data)
                    self.handle_message(conn, message)
                except pickle.UnpicklingError:
                    pass
                except ConnectionResetError as e:
                    print("Client {} disconnected.".format(conn.address))
                    conn.disconnect()
                    player_info = conn.player.dump_info()


class GameClient:
    def __init__(self, server_address):
        self.player = None
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect(server_address)
        self.game = Game()

        data = self.client_socket.recv(BUFFER_SIZE)
        message = pickle.loads(data)
        self.handle_message(message)

        pygame.init()
        screen_size = (800, 600)

        self.clock = pygame.time.Clock()
        self.display = pygame.display.set_mode(screen_size)
        pygame.display.set_caption('2D Multiplayer Test')

        self.done = False
        self.listening_thread = threading.Thread(target=self.listen_to_server)
        self.listening_thread.daemon = True
        self.listening_thread.start()

    def listen_to_server(self):
        while not self.done:
            data = self.client_socket.recv(BUFFER_SIZE)

            if data:
                message = pickle.loads(data)
                self.handle_message(message)

    def handle_message(self, message):
        if message.type == MessageType.NEW_PLAYER_INFO:
            player_info = message.data
            self.player = Player(player_info['id'])
            self.player.load_info(player_info)
            self.player.state = PlayerState.CURRENT
            self.game.players.append(self.player)
        elif message.type == MessageType.GAME_INFO_SEND:
            player_info = self.player.dump_info()
            player_info['state'] = PlayerState.ONLINE
            game_info = message.data
            self.game.load_info(game_info)
            player_info['state'] = PlayerState.CURRENT
            self.player.load_info(player_info)

    def loop(self):
        while not self.done:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.done = True
                self.player.control(event)

            #self.game.draw(self.display,
            #               self.player.rect.center + self.player.position)
            self.game.draw(self.display, pygame.math.Vector2(0, 0))

            self.game.update()
            self.player.turn_to(mouse)
            pygame.display.update()

            self.clock.tick(60)

            message = Message(MessageType.PLAYER_INFO, self.player.dump_info())
            data = pickle.dumps(message)
            self.client_socket.sendall(data)

        pygame.quit()


def main():
    server_address = ('localhost', 12345)
    if input('[s/c] ') == 's':
        game_server = GameServer(server_address)
        game_server.loop()
    else:
        game_client = GameClient(server_address)
        game_client.loop()


if __name__ == "__main__":
    main()
