from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from app.features.travel.trips import forecast as fc
from app.features.travel.trips.forecast import a_year_earlier, days_from_daily, pick_mode
from app.features.travel.trips.forecast_service import TripForecastService

TODAY = date(2026, 12, 10)


class TestPickMode:
    def test_forecast_within_two_weeks_of_the_start(self):
        assert pick_mode(date(2026, 12, 20), TODAY) == "forecast"

    def test_ongoing_trip_uses_the_forecast(self):
        assert pick_mode(date(2026, 12, 5), TODAY) == "forecast"

    def test_far_trip_uses_last_years_climate(self):
        assert pick_mode(date(2027, 3, 1), TODAY) == "climate"


def test_a_year_earlier_handles_leap_day():
    assert a_year_earlier(date(2028, 2, 29)) == date(2027, 2, 28)
    assert a_year_earlier(date(2027, 3, 1)) == date(2026, 3, 1)


class TestDaysFromDaily:
    def test_rows_are_labelled_with_the_trips_dates_and_rain_has_a_threshold(self):
        daily = {"temperature_2m_min": [1.0, 2.0], "temperature_2m_max": [5.0, 6.0], "precipitation_sum": [0.4, 3.0]}
        days = days_from_daily(daily, [date(2027, 3, 1), date(2027, 3, 2)])
        assert [(d.date, d.min_c, d.max_c, d.rain) for d in days] == [
            (date(2027, 3, 1), 1.0, 5.0, False), (date(2027, 3, 2), 2.0, 6.0, True)]

    def test_missing_columns_become_none(self):
        days = days_from_daily({}, [date(2027, 3, 1)])
        assert days[0].min_c is None and days[0].rain is False


def _stay(city="Beta", lat=None, lng=None, check_in=datetime(2026, 12, 17, 14), check_out=datetime(2026, 12, 19, 10)):
    return SimpleNamespace(place=SimpleNamespace(city=city, country="Testland", lat=lat, lng=lng),
                           check_in_at=check_in, check_out_at=check_out, timezone="UTC")


def _leg(origin, destination, departs_at, arrives_at):
    return SimpleNamespace(origin=origin, destination=destination, departs_at=departs_at.replace(tzinfo=timezone.utc),
                           arrives_at=arrives_at.replace(tzinfo=timezone.utc), departs_tz="UTC", arrives_tz="UTC")


class FakeWeatherRepo:
    """The saved-weather table in memory: upsert replaces by (city_key, day)."""

    def __init__(self):
        self.rows: dict[tuple[str, date], SimpleNamespace] = {}

    async def get_weather(self, trip_id):
        return list(self.rows.values())

    async def upsert_weather(self, trip_id, rows):
        for row in rows:
            self.rows[row["city_key"], row["day"]] = SimpleNamespace(**row)


@pytest.fixture
def service():
    svc = TripForecastService(AsyncMock(), AsyncMock())
    svc._client, svc._trips, svc._stays, svc._legs = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._weather = FakeWeatherRepo()
    svc._legs.get_legs.return_value = []
    svc._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 19))
    svc._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0)]
    svc._client.fetch_range.return_value = {
        "temperature_2m_min": [1, 1, 1], "temperature_2m_max": [4, 4, 4], "precipitation_sum": [0, 5, 0]}
    return svc


@freeze_time("2026-12-10 12:00:00")
class TestService:
    async def test_forecast_for_each_stay_city_using_place_coordinates(self, service):
        result = await service.get_forecast(1)
        assert result.mode == "forecast" and result.available
        assert [d.rain for d in result.cities[0].days] == [False, True, False]
        service._client.geocode.assert_not_awaited()
        assert service._client.fetch_range.await_args.kwargs["archive"] is False

    async def test_each_city_only_gets_the_days_the_trip_is_there(self, service):
        service._stays.get_stays.return_value = [
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 17, 14), datetime(2026, 12, 18, 10)),
            _stay("Gamma", 3.0, 4.0, datetime(2026, 12, 18, 15), datetime(2026, 12, 19, 10)),
        ]
        result = await service.get_forecast(1)
        days = {c.city: [d.date.day for d in c.days] for c in result.cities}
        assert days == {"Beta": [17, 18], "Gamma": [18, 19]}

    async def test_a_city_in_two_separate_stays_skips_the_days_between(self, service):
        service._stays.get_stays.return_value = [
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 17, 14), datetime(2026, 12, 17, 20)),
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 19, 8), datetime(2026, 12, 19, 20)),
        ]
        result = await service.get_forecast(1)
        assert [d.date.day for d in result.cities[0].days] == [17, 19]

    async def test_cities_without_coordinates_are_geocoded_by_name(self, service):
        service._stays.get_stays.return_value = [_stay(lat=None)]
        service._client.geocode.return_value = {"latitude": 3.0, "longitude": 4.0}
        await service.get_forecast(1)
        service._client.geocode.assert_awaited_once_with("Beta, Testland")

    async def test_far_trips_read_the_archive_for_last_year(self, service):
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2027, 3, 1), end_date=date(2027, 3, 3))
        service._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0, check_in=datetime(2027, 3, 1, 14), check_out=datetime(2027, 3, 3, 10))]
        result = await service.get_forecast(1)
        assert result.mode == "climate"
        args = service._client.fetch_range.await_args
        assert args.args[2] == date(2026, 3, 1) and args.kwargs["archive"] is True
        assert result.cities[0].days[0].date == date(2027, 3, 1)

    async def test_weather_service_failure_degrades_to_a_message(self, service):
        service._client.fetch_range.side_effect = RuntimeError("503")
        result = await service.get_forecast(1)
        assert result.available is False and "not available" in result.message

    async def test_no_stays_and_no_legs_no_forecast(self, service):
        service._stays.get_stays.return_value = []
        assert (await service.get_forecast(1)).available is False

    async def test_trip_ends_get_their_own_tiles_and_layovers_none(self, service):
        service._legs.get_legs.return_value = [
            _leg("Alpha", "Omega", datetime(2026, 12, 17, 8), datetime(2026, 12, 17, 10)),
            _leg("Omega", "Alpha", datetime(2026, 12, 19, 18), datetime(2026, 12, 19, 20))]
        result = await service.get_forecast(1)
        days = {c.city: [d.date.day for d in c.days] for c in result.cities}
        assert days == {"Beta": [17, 18, 19], "Alpha": [17, 19]}  # the layover city Omega gets nothing

    async def test_origin_city_comes_first_and_destination_city_last(self, service):
        service._legs.get_legs.return_value = [_leg("Alpha", "Omega", datetime(2026, 12, 17, 8), datetime(2026, 12, 19, 10))]
        service._client.geocode.return_value = {"latitude": 3.0, "longitude": 4.0}
        result = await service.get_forecast(1)
        assert [c.city for c in result.cities] == ["Alpha", "Beta", "Omega"]

    async def test_a_home_city_at_both_ends_comes_first_before_the_stay_cities(self, service):
        service._legs.get_legs.return_value = [
            _leg("Alpha", "Omega", datetime(2026, 12, 17, 8), datetime(2026, 12, 17, 10)),
            _leg("Omega", "Alpha", datetime(2026, 12, 19, 18), datetime(2026, 12, 19, 20))]
        service._client.geocode.return_value = {"latitude": 3.0, "longitude": 4.0}
        result = await service.get_forecast(1)
        assert [c.city for c in result.cities] == ["Alpha", "Beta"]

    async def test_a_home_city_at_both_ends_is_one_row_without_stays(self, service):
        service._stays.get_stays.return_value = []
        service._legs.get_legs.return_value = [
            _leg("Alpha", "Omega", datetime(2026, 12, 17, 8), datetime(2026, 12, 17, 10)),
            _leg("Omega", "Alpha", datetime(2026, 12, 19, 18), datetime(2026, 12, 19, 20))]
        service._client.geocode.return_value = {"latitude": 3.0, "longitude": 4.0}
        result = await service.get_forecast(1)
        assert [(c.city, [d.date.day for d in c.days]) for c in result.cities] == [("Alpha", [17, 19])]

    async def test_an_end_city_that_is_a_stay_city_shares_its_row(self, service):
        service._legs.get_legs.return_value = [_leg("Alpha", "beta", datetime(2026, 12, 17, 8), datetime(2026, 12, 17, 10))]
        result = await service.get_forecast(1)
        assert [c.city for c in result.cities].count("Beta") == 1

    async def test_a_second_call_the_same_day_reads_the_table_not_open_meteo(self, service):
        await service.get_forecast(1)
        again = await service.get_forecast(1)
        assert service._client.fetch_range.await_count == 1
        assert [d.rain for d in again.cities[0].days] == [False, True, False]
        assert again.as_of == TODAY

    async def test_the_next_day_overwrites_the_saved_days(self, service):
        await service.get_forecast(1)
        service._client.fetch_range.return_value = {
            "temperature_2m_min": [0, 0, 0], "temperature_2m_max": [9, 9, 9], "precipitation_sum": [0, 0, 0]}
        with freeze_time("2026-12-11 12:00:00"):
            result = await service.get_forecast(1)
        assert service._client.fetch_range.await_count == 2
        assert [d.max_c for d in result.cities[0].days] == [9, 9, 9] and result.as_of == date(2026, 12, 11)

    async def test_days_that_have_passed_keep_their_last_forecast(self, service):
        await service.get_forecast(1)
        service._client.fetch_range.return_value = {
            "temperature_2m_min": [0, 0], "temperature_2m_max": [9, 9], "precipitation_sum": [0, 0]}
        with freeze_time("2026-12-18 12:00:00"):  # the 17th is over: only the 18th and 19th are refreshed
            result = await service.get_forecast(1)
        assert service._client.fetch_range.await_args.args[2] == date(2026, 12, 18)
        assert [(d.date.day, d.max_c) for d in result.cities[0].days] == [(17, 4), (18, 9), (19, 9)]

    async def test_a_finished_trip_is_served_from_the_table_without_open_meteo(self, service):
        await service.get_forecast(1)
        service._client.fetch_range.reset_mock()
        with freeze_time("2026-12-30 12:00:00"):
            result = await service.get_forecast(1)
        service._client.fetch_range.assert_not_awaited()
        assert result.finished and result.available and result.mode == "forecast"
        assert [d.max_c for d in result.cities[0].days] == [4, 4, 4]

    async def test_a_recent_finished_trip_with_nothing_saved_is_filled_once_from_the_normal_endpoint(self, service):
        with freeze_time("2026-12-30 12:00:00"):
            first = await service.get_forecast(1)
            again = await service.get_forecast(1)
        assert service._client.fetch_range.await_count == 1
        args = service._client.fetch_range.await_args
        assert args.args[2] == date(2026, 12, 17) and args.kwargs["archive"] is False  # recent: the normal endpoint, the trip's own dates
        assert first.finished and first.mode == "actual" and [d.max_c for d in again.cities[0].days] == [4, 4, 4]
        assert {r.source for r in service._weather.rows.values()} == {"actual"}

    async def test_an_old_finished_trip_is_filled_from_the_archive(self, service):
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 19))
        with freeze_time("2027-06-30 12:00:00"):
            result = await service.get_forecast(1)
        assert service._client.fetch_range.await_args.kwargs["archive"] is True and result.mode == "actual"

    async def test_a_trip_straddling_the_reach_uses_the_archive_for_old_days_and_the_normal_endpoint_for_recent_ones(self, service):
        service._client.fetch_range.return_value = {"temperature_2m_min": [1], "temperature_2m_max": [4], "precipitation_sum": [0]}
        service._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0, check_in=datetime(2026, 12, 17, 14), check_out=datetime(2026, 12, 18, 10))]
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 18))
        with freeze_time("2027-03-18 12:00:00"):  # 90 days back is 18 Dec: the 17th is older, the 18th is in reach
            result = await service.get_forecast(1)
        calls = [(c.args[2], c.kwargs["archive"]) for c in service._client.fetch_range.await_args_list]
        assert calls == [(date(2026, 12, 17), True), (date(2026, 12, 18), False)]
        assert [d.date.day for d in result.cities[0].days] == [17, 18]

    async def test_only_the_days_never_saved_are_backfilled_and_the_mode_is_mixed(self, service):
        await service.get_forecast(1)
        del service._weather.rows["beta", date(2026, 12, 18)]
        service._client.fetch_range.reset_mock()
        service._client.fetch_range.return_value = {
            "temperature_2m_min": [0], "temperature_2m_max": [7], "precipitation_sum": [0]}
        with freeze_time("2026-12-30 12:00:00"):
            result = await service.get_forecast(1)
        args = service._client.fetch_range.await_args
        assert args.args[2] == date(2026, 12, 18) and args.args[3] == date(2026, 12, 18)
        assert result.mode == "mixed" and [d.max_c for d in result.cities[0].days] == [4, 7, 4]

    async def test_archive_days_without_values_are_not_saved_so_they_are_asked_again(self, service):
        service._client.fetch_range.return_value = {
            "temperature_2m_min": [None, None, None], "temperature_2m_max": [None, None, None], "precipitation_sum": [None, None, None]}
        with freeze_time("2026-12-20 12:00:00"):
            result = await service.get_forecast(1)
        assert result.mode == "none" and service._weather.rows == {}

    async def test_archive_failure_on_a_finished_trip_hides_the_card_and_saves_nothing(self, service):
        service._client.fetch_range.side_effect = RuntimeError("503")
        with freeze_time("2026-12-30 12:00:00"):
            result = await service.get_forecast(1)
        assert result.available is False and result.mode == "none" and service._weather.rows == {}

    async def test_open_meteo_failure_serves_the_older_snapshot(self, service):
        await service.get_forecast(1)
        service._client.fetch_range.side_effect = RuntimeError("503")
        with freeze_time("2026-12-11 12:00:00"):
            result = await service.get_forecast(1)
        assert result.available and result.as_of == TODAY

    async def test_far_trips_save_climate_rows(self, service):
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2027, 3, 1), end_date=date(2027, 3, 3))
        service._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0, check_in=datetime(2027, 3, 1, 14), check_out=datetime(2027, 3, 3, 10))]
        await service.get_forecast(1)
        assert {r.source for r in service._weather.rows.values()} == {"climate"}

    async def test_unknown_trip(self, service):
        service._trips.get_trip.return_value = None
        assert await service.get_forecast(9) is None
