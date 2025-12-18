-- Database setup for HearMeOut Game Leaderboard
-- Run this in phpMyAdmin or MySQL command line

-- Create database
CREATE DATABASE IF NOT EXISTS hearmeout_db;
USE hearmeout_db;

-- Create leaderboard table
CREATE TABLE IF NOT EXISTS leaderboard (
    id INT AUTO_INCREMENT PRIMARY KEY,
    player_name VARCHAR(100) NOT NULL,
    score INT NOT NULL,
    game VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_score (score DESC),
    INDEX idx_player (player_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert sample data (optional)
INSERT INTO leaderboard (player_name, score, game) VALUES
('Ayan', 1250, 'Knowledge Check'),
('Sarah', 980, 'Storytelling'),
('Alex', 875, 'Riddle Challenge');

