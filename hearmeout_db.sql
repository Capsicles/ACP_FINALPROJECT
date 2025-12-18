-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Dec 09, 2025 at 10:53 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `hearmeout.db`
--

-- --------------------------------------------------------

--
-- Table structure for table `leaderboard`
--

CREATE TABLE `leaderboard` (
  `id` int(11) NOT NULL,
  `player_name` varchar(100) NOT NULL,
  `score` int(11) NOT NULL,
  `game` varchar(100) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `user_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `leaderboard`
--

INSERT INTO `leaderboard` (`id`, `player_name`, `score`, `game`, `created_at`, `user_id`) VALUES
(63, 'mimi', 0, 'All', '2025-12-09 09:43:16', 2),
(64, 'hanz', 0, 'All', '2025-12-09 09:43:16', 3),
(65, 'ayan', 0, 'All', '2025-12-09 09:43:16', 4);

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `username` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('user','admin') NOT NULL DEFAULT 'user',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `username`, `password_hash`, `role`, `created_at`) VALUES
(1, 'admin', 'scrypt:32768:8:1$Vfm83QF02LEDbooU$027cbe1d10ef95e51118e83512e67e992de4f73d86b6b9ffe0029c4c147fc6e08952273192271eb14e97e6b644a361724726aee38981ed9d15ffab695f711958', 'admin', '2025-12-07 05:49:12'),
(2, 'mimi', 'scrypt:32768:8:1$ILWXs1V0kc0rglOA$58c03d16e0689a0baf61b5751dc43535aae84027684d4cc3d8876d3c96c9f4426983af238c3bb6abda194ecedc217b824c908b41ebd79d23f59a50154df78a40', 'user', '2025-12-07 06:08:52'),
(3, 'hanz', 'scrypt:32768:8:1$CPCMe0oB9M0Zo884$276b9164586b53c70aeb7228df796ca05c43fefa3eb3f026d33452905f13e202d6436fb3c5d0e344e0122525d518b9917ae1fe53ceba71d97611e1b4e2f10f8e', 'user', '2025-12-09 03:27:32'),
(4, 'ayan', 'scrypt:32768:8:1$aJzcdHWiOXWpqQEm$ffaebbdda3ebaad01c085b15ebec6d2d03aa9ea076917e4d3ca51bbff4d573d63d93483930db07fda90753a37ade495650659d7a67ab0054a83f246c63edc4e1', 'user', '2025-12-09 09:25:54');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `leaderboard`
--
ALTER TABLE `leaderboard`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_score` (`score`),
  ADD KEY `idx_player` (`player_name`),
  ADD KEY `idx_user` (`user_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `leaderboard`
--
ALTER TABLE `leaderboard`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=66;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
