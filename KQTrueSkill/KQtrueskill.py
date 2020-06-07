import copy
import filecmp
import datetime
import trueskill
from trueskill import *
import csv


class KQTrueSkill:
    datetime_format: str = "%Y-%m-%dT%H:%M:%S%z"

    def __init__(self):
        trueskill.setup(trueskill.MU, trueskill.SIGMA, trueskill.BETA, trueskill.TAU, draw_probability=0)
        self.snapshots = {}  # self.snapshots[tournament] = {'playername' = , 'trueskill' = }
        self.matches: [] = []
        self.playerscenes = {}
        self.playerteams = {}
        self.playerratings = {}
        self.playertournaments = {}  # playertournaments[playername] = ["BB4","KQ30",...]
        self.playergames = {}
        self.playerwins = {}
        self.playerlosses = {}
        self.incomplete_players = []  # list of playernames w/0 scenes
        self.tournaments = []
        self.tournamentdates = {}  # source data only ties matches directly to a date.
        self.teams = {}  # [tournament][team name] = {p1, p2, p3...}
        self.output_file_name: str = '../PlayerSkill.csv'
        self.process_approved_datasets()

    # ingest the known good datasets automatically
    def process_approved_datasets(self):
        self.ingest_dataset('datasets/2019 KQ - 2019 Players.csv', 'datasets/2019 KQ - 2019 game results.csv')
        self.ingest_dataset('datasets/2018 KQ - GDC3 Players.csv', 'datasets/2018 KQ - GDC3 game results.csv')
        self.ingest_dataset('datasets/2018 KQ - BB3 Players.csv', 'datasets/2018 KQ - BB3 game results.csv')
        self.ingest_dataset('datasets/2018 KQ - HH1 Players.csv', 'datasets/2018 KQ - HH1 game results.csv')
        self.ingest_dataset('datasets/2018 - CC1 Players.csv', 'datasets/2018 - CC1 game results.csv')
        self.ingest_dataset('datasets/2019 - CC2 Players.csv', 'datasets/2019 - CC2 game results.csv')
        self.ingest_dataset('datasets/2020 - CC3 Players.csv', 'datasets/2020 - CC3 game results.csv')
        self.ingest_dataset('datasets/2018 Midwest players.csv', 'datasets/2018 Midwest game results.csv')
        self.ingest_dataset('datasets/Coronation players.csv', 'datasets/2017 Coronation game results.csv')
        self.ingest_dataset('datasets/2019 misc players.csv', 'datasets/2019 misc game results.csv')

        # run trueskill on the matches
        self.calculate_trueskills()

    def test_dataset(self, player_file, results_file):
        self.ingest_dataset(player_file, results_file)
        # todo report teams with no matches
        # todo combine datasets into one file
        # self.calculate_trueskills()

    def ingest_dataset(self, playerfile: str, matchfile: str):
        # must ingest players first
        # reports new players found in this file
        self.ingest_players_from_file(playerfile)

        # expect Exceptions if your team names don't match
        self.ingest_matches_from_file(matchfile)

        # ensure matches will always process in historical order
        self.matches = sorted(self.matches, key=lambda match: match["time"])

    # wipe old ratings objects and recalculate trueskill, compare new result with old ratings
    # side effect: update player games & w/l counts
    def calculate_trueskills(self):
        # save old ratings for later comparison
        old_playerratings = self.playerratings

        # make clean ratings objects
        self.playerratings = {}
        for player in self.playerteams.keys():
            self.playerratings[player] = Rating()

        # calculate complete history
        current_tournament: str = ''
        for m in self.matches:
            t1ratings = []
            t2ratings = []
            tournament: str = m['tournament']
            team1name: str = m['team1name']
            team2name: str = m['team2name']
            team1wins: int = m['team1wins']
            team2wins: int = m['team2wins']

            if current_tournament != tournament:
                self.record_trueskill_snapshot(current_tournament)
                current_tournament = tournament
                print(f"processing {tournament}")

            # Trueskill wants arrays of ratings objects for each player
            # Order doesn't matter to trueskill, but it does matter to us, so preserve order as found in
            # the teams collection
            for player in self.teams[tournament][team1name]:
                t1ratings.append(self.playerratings[player])
                self.playergames[player] += team1wins + team2wins
                self.playerwins[player] += team1wins
                self.playerlosses[player] += team2wins
            for player in self.teams[tournament][team2name]:
                t2ratings.append(self.playerratings[player])
                self.playergames[player] += team1wins + team2wins
                self.playerwins[player] += team2wins
                self.playerlosses[player] += team1wins

            # update ratings for each game win
            for x in range(team1wins):
                t1ratings, t2ratings = rate([t1ratings, t2ratings], ranks=[0, 1])

            for x in range(team2wins):
                t1ratings, t2ratings = rate([t1ratings, t2ratings], ranks=[1, 0])

            # now put the ratings back into the main dict
            for i in range(5):
                self.playerratings[self.teams[tournament][team1name][i]] = t1ratings[i]
            for i in range(5):
                self.playerratings[self.teams[tournament][team2name][i]] = t2ratings[i]
        self.record_trueskill_snapshot(current_tournament)

        # log diifferences in new and old ratings
        # self.compare_ratings(old_playerratings, self.playerratings)

    def compare_ratings(self, old_playerratings, playerratings):
        new_players = []
        removed_players = []
        shared_player_deltas = {}

        for p in old_playerratings.keys():
            if p in playerratings.keys():
                shared_player_deltas[
                    p] = f"mu: {playerratings[p].mu - old_playerratings[p].mu}, s: {playerratings[p].sigma - old_playerratings[p].sigma}"
            else:
                removed_players.append(p)

        for p in playerratings.keys():
            if p not in old_playerratings.keys():
                new_players.append(p)

        print(f"New Players: {new_players}")
        print(f"Removed players: {removed_players}")
        print(f"Changed players: {shared_player_deltas}")

    def ingest_players_from_file(self, filename: str):
        with open(filename) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            last_seen_team = None
            for row in csv_reader:
                if line_count == 0:
                    print(f'Player List Column names are {", ".join(row)}')
                    line_count += 1
                else:
                    line_count += 1
                    tournament = row[0]
                    playerteam = row[1]
                    playername = row[2]
                    playerscene = row[3]

                    if playerteam is None or playerteam.strip() == '':
                        playerteam = last_seen_team
                    else:
                        last_seen_team = playerteam
                    self.add_player(playername, playerscene, playerteam, tournament)
            print(f'Processed {line_count} players from {filename}.')
            # print(f'Player Scenes: {self.playerscenes}')
            # print(f'****TEAMS: {self.teams}')

    def add_player(self, playername, playerscene, playerteam, tournament):
        if tournament not in self.tournaments:
            self.tournaments.append(tournament)
            self.teams[tournament] = {}

        if playerteam is None or playerteam.strip() == '':
            raise Exception(f"{tournament}: empty team")

        if playerteam in self.teams[tournament].keys():
            if playername is None or playername == '':
                playername = playerteam + f" {len(self.teams[tournament][playerteam]) + 1}"
                playerscene = None
            self.teams[tournament][playerteam].append(playername)
        else:
            if playername is None or playername == '':
                self.incomplete_players.append(f"{tournament}: {playerteam}, {playername}, {playerscene}")
                playername = playerteam + " 1"
                playerscene = None
            self.teams[tournament][playerteam] = [playername]

        self.playerscenes[playername] = playerscene

        if playername in self.playerteams.keys():
            self.playerteams[playername][tournament] = playerteam
        else:
            self.playerteams[playername] = {tournament: playerteam}

        if playername in self.playertournaments.keys():
            self.playertournaments[playername].append(tournament)
        else:
            self.playertournaments[playername] = [tournament]

        self.playergames[playername] = 0
        self.playerwins[playername] = 0
        self.playerlosses[playername] = 0

        # elif playerscene is None or playerscene.strip() == '':
        #     self.incomplete_players.append(f"{tournament}: {playerteam}, {playername}, {playerscene}")

    # side effect: updates tournament dates with dates found here
    def ingest_matches_from_file(self, filename: str):
        with open(filename) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            errors = ''
            for row in csv_reader:
                if line_count == 0:
                    # print(f' Game Results Column names are {", ".join(row)}')
                    line_count += 1
                else:
                    # print(f'\t{row[0]}, {row[1]}, {row[2]}, {row[3]}, {row[4]}, {row[5]}, {row[6]}.')
                    tournament = row[0]
                    bracket = row[1]
                    team1name = row[2]
                    team2name = row[3]
                    team1wins = int(row[4])
                    team2wins = int(row[5])
                    time = datetime.datetime.strptime(row[6], self.datetime_format)

                    # we should not be adding any new members to our tourney/team lists here
                    if tournament not in self.tournaments:
                        errors += f"{tournament} not found in self.tournaments. tournaments found = {self.tournaments}\n"
                    if team1name not in self.teams[tournament].keys():
                        errors += f"{team1name} not found in teams[{tournament}]. team 2 was {team2name}. teams found = {self.teams[tournament].keys()}\n"
                    if team2name not in self.teams[tournament].keys():
                        errors += f"{team2name} not found in teams[{tournament}]. team 1 was {team1name}. teams found = {self.teams[tournament].keys()}\n"

                    # track the date for this tournament, if not already tracked
                    if tournament not in self.tournamentdates.keys():
                        self.tournamentdates[tournament] = time.date()
                        print(f"sat {tournament} date to {time.strftime(KQTrueSkill.datetime_format)}")

                    self.matches.append(
                        {"tournament": tournament,
                         "bracket": bracket,
                         "team1name": team1name,
                         "team2name": team2name,
                         "team1wins": team1wins,
                         "team2wins": team2wins,
                         "time": time,
                         })
                    line_count += 1
        print(f"Processed {line_count - 1} matches, now tracking {len(self.matches)} matches.")
        if errors != '':
            raise Exception(errors)

    def write_player_ratings(self, filename: str = None):
        if filename is None:
            filename = self.output_file_name

        # make sure our csv rows align
        num_tourneys = len(self.tournaments)
        tourneylist = sorted(self.tournaments, key=lambda t: self.tournamentdates[t])

        headers = ['Player Name', 'scene', 'trueskill', 'tourneys', 'games', 'wins', 'losses', 'win%']
        headers += tourneylist * 2

        with open(filename, mode='w') as playerskillfile:
            playerskill_writer = csv.writer(playerskillfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            playerskill_writer.writerow(headers)
            for player in sorted(self.playerratings.keys()):
                try:
                    row = [player,
                       self.playerscenes[player],
                       self.playerratings[player].mu - 3 * self.playerratings[player].sigma,
                       len(self.playertournaments[player]),
                       self.playergames[player],
                       self.playerwins[player],
                       self.playerlosses[player],
                       "%.2f" % (self.playerwins[player] / self.playergames[player]),
                       ]
                    for t in tourneylist:
                        if t in self.playertournaments[player]:
                            row.append(t + " / " + self.playerteams[player][t])
                        else:
                            row.append('')
                    for t in tourneylist:
                        if self.snapshots[t][player].mu == trueskill.MU and self.snapshots[t][player].sigma == trueskill.SIGMA:
                            row.append('')
                        else:
                            row.append(self.snapshots[t][player].mu - 3*self.snapshots[t][player].sigma)
                    playerskill_writer.writerow(row)
                except Exception as e:
                    print(f"{player}, {self.playerscenes[player]}, {self.playergames[player]}, {self.playerteams[player]}: {e}")
                    raise Exception(e)


    def get_player_scene_list(self):
        playerlist = []

        for playername in self.playerteams.keys():
            playerlist.append(f"{playername} / {self.playerscenes[playername]}")

        return playerlist

    def print_known_tournaments(self):
        printable_tournaments = {}
        for t in self.tournamentdates.keys():
            date: datetime.date = self.tournamentdates[t]
            if date.year in printable_tournaments.keys():
                printable_tournaments[date.year].append(t)
            else:
                printable_tournaments[date.year] = [t]
            printable_tournaments[date.year] = sorted(printable_tournaments[date.year],
                                                      key=lambda tourney: self.tournamentdates[tourney])
        for y in sorted(printable_tournaments.keys()):
            print(f"{y}: {printable_tournaments[y]}")

    def print_data_errors(self):
        # match errors are tracked during data scrubbing. known match errors hard coded into README
        # missing players should have an empty scene, so display players with empty scenes here
        for p in self.incomplete_players:
            print(p)

    def record_trueskill_snapshot(self, tournament):
        self.snapshots[tournament] = copy.deepcopy(self.playerratings)


def main():
    history: KQTrueSkill = KQTrueSkill()

    # stuff to copy into README
    history.print_known_tournaments()
    print("\n*************************\n")
    history.print_data_errors()

    # print your player ratings
    history.write_player_ratings()

    # print(f'Player Ratings: {history.playerratings}')

    # test whether processing changed values
    if filecmp.cmp("PlayerSkill.old.csv", history.output_file_name):
        print("Files are same")
    else:
        print("Files are different")


if __name__ == '__main__':
    main()
